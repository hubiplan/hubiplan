"""Schreiben über die API für andere Programme (docs/api.md, Stufe 3).

Grundsätze: Jeder schreibende Bereich wird einzeln angekreuzt. Geschrieben wird nur
Unkritisches (Termin, Ergebnis, Anwesenheit) oder ein Vorschlag bzw. Entwurf, den ein Mensch
in HUBIplan übernimmt (Mitgliederdaten, Rundschreiben). Nichts wird gelöscht und nichts
versendet. Ändern darf ein Zugang nur, was er selbst angelegt hat (``WrittenRecord``). Im
Änderungsprotokoll steht „API-Zugang ‹Name›“ statt einer Person.

Kopfzeile ``Idempotency-Key``: Dieselbe Anfrage mit demselben Schlüssel legt innerhalb von
24 Stunden nichts doppelt an und bekommt dieselbe Antwort. ``external_id`` ist die eigene
Kennung des Dritten; sie ist je Zugang und Art eindeutig und lässt sich nachschlagen.
"""

from __future__ import annotations

import hashlib
import json

from django.db import transaction
from django.db.models import F
from django.http import Http404
from django.utils import timezone
from django.utils.translation import gettext as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from audit.log import diff, record, snapshot
from changes import tracking
from core.tenancy import org_context

from . import refs
from . import scopes as sc
from . import views as base
from .auth import Problem
from .models import IDEMPOTENCY_KEEP, ApiAccess, IdempotencyKey, WrittenRecord
from .personal import PersonalView, log_read
from .views import ERRORS, PartnerProblemSerializer, PartnerView

EVENT = "event"
TRAINING = "training"
STARTER = "starter"
PROPOSAL = "proposal"
CIRCULAR = "circular"
KINDS = (EVENT, TRAINING, PROPOSAL, CIRCULAR)

MAX_RESULTS = 500
MAX_ATTENDANCE = 1000
# Offene Vorschläge: je Mitglied und je Zugang
MAX_OPEN_PER_MEMBER = 3
MAX_OPEN_PER_ACCESS = 200
# Entwürfe von Rundschreiben, die noch niemand versendet oder gelöscht hat
MAX_DRAFTS = 20

WRITE_ERRORS = {
    400: PartnerProblemSerializer,
    409: PartnerProblemSerializer,
    **ERRORS,
}
IDEMPOTENCY_NOTE = (
    " Mit der Kopfzeile ``Idempotency-Key`` legt eine wiederholte Anfrage nichts doppelt an."
)

EXTERNAL_ID = {
    "max_length": 100,
    "required": False,
    "allow_blank": True,
    "help_text": "eigene Kennung des Dritten, je Zugang eindeutig",
}


# --- Gemeinsames ---


def written(access: ApiAccess, kind: str, object_id) -> WrittenRecord | None:
    """Hat dieser Zugang den Datensatz angelegt?"""
    try:
        pk = int(object_id)
    except (TypeError, ValueError):
        return None
    return WrittenRecord.objects.filter(access=access, kind=kind, object_id=pk).first()


def check_external(access: ApiAccess, kind: str, external_id: str) -> None:
    """Die eigene Kennung gibt es schon: 409 mit der Kennung des vorhandenen Datensatzes."""
    if not external_id:
        return
    found = WrittenRecord.objects.filter(access=access, kind=kind, external_id=external_id).first()
    if found is not None:
        raise Problem(
            409,
            "external_id_exists",
            _("Diese eigene Kennung ist schon vergeben"),
            id=str(found.object_id),
            external_id=external_id,
        )


def remember(access: ApiAccess, kind: str, object_id: int, external_id: str = "") -> None:
    with tracking.suppress():
        WrittenRecord.objects.create(
            organization=access.organization,
            access=access,
            kind=kind,
            object_id=object_id,
            external_id=external_id or "",
        )


def _fingerprint(request) -> str:
    body = json.dumps(request.data, sort_keys=True, default=str, ensure_ascii=False)
    text = f"{request.method}\n{request.path}\n{body}"
    return hashlib.sha256(text.encode()).hexdigest()


class WriteMixin:
    """Schreibende Anfrage ausführen: im Datenbereich der Einheit, ganz oder gar nicht, mit
    Wiederholungsschutz. ``action`` liefert (Status, Antwort)."""

    def run(self, request, action) -> Response:
        key = (request.headers.get("Idempotency-Key") or "").strip()
        if len(key) > 100:
            raise serializers.ValidationError({"Idempotency-Key": _("Höchstens 100 Zeichen.")})
        with org_context(self.org), transaction.atomic():
            stored = None
            if key:
                fingerprint = _fingerprint(request)
                with tracking.suppress():
                    stored, created = IdempotencyKey.objects.select_for_update().get_or_create(
                        access=self.access,
                        key=key,
                        defaults={"organization": self.org, "fingerprint": fingerprint},
                    )
                fresh = stored.created_at > timezone.now() - IDEMPOTENCY_KEEP
                if not created and fresh:
                    if stored.fingerprint != fingerprint:
                        raise Problem(
                            409,
                            "idempotency_conflict",
                            _("Dieser Idempotency-Key gehört zu einer anderen Anfrage"),
                        )
                    response = Response(stored.body, status=stored.status)
                    response["Idempotency-Replayed"] = "true"
                    return response
                if not created:
                    stored.fingerprint, stored.created_at = fingerprint, timezone.now()
            status, body = action()
            body = json.loads(JSONRenderer().render(body))
            with tracking.suppress():
                if stored is not None:
                    stored.status, stored.body = status, body
                    stored.save()
                ApiAccess.objects.filter(pk=self.access.pk).update(
                    write_count=F("write_count") + 1, last_write_at=timezone.now()
                )
        return Response(body, status=status)

    def chosen_unit(self, raw):
        """Untereinheit aus der Anfrage; ein Zugang für eine Untereinheit bleibt darin."""
        from organizations.models import Department
        from organizations.tree import subtree_ids

        if raw in (None, ""):
            return self.unit
        unit = Department.objects.filter(organization=self.org, uuid=raw, is_active=True).first()
        if unit is None or (self.unit is not None and unit.pk not in subtree_ids(self.unit)):
            raise ValidationError({"unit": _("Diese Untereinheit gibt es hier nicht.")})
        return unit

    def in_reach(self, department_id) -> bool:
        from organizations.tree import subtree_ids

        return self.unit is None or department_id in subtree_ids(self.unit)


# --- Eigene Kennung nachschlagen ---


class PartnerExternalIdSerializer(serializers.Serializer):
    kind = serializers.CharField()
    id = serializers.CharField()
    external_id = serializers.CharField()


class ExternalIdView(PartnerView):
    @extend_schema(
        operation_id="external_id",
        summary="Datensatz zur eigenen Kennung",
        description=(
            "Kennung des Datensatzes, den dieser Zugang mit der eigenen Kennung "
            "``external_id`` angelegt hat; sonst 404."
        ),
        parameters=[
            OpenApiParameter(
                "kind",
                OpenApiTypes.STR,
                required=True,
                description="event, training, proposal oder circular",
            ),
            OpenApiParameter("external_id", OpenApiTypes.STR, required=True),
        ],
        responses={200: PartnerExternalIdSerializer, 404: PartnerProblemSerializer, **ERRORS},
    )
    def get(self, request):
        kind = request.query_params.get("kind", "")
        external_id = request.query_params.get("external_id", "")
        if kind not in KINDS or not external_id:
            raise Http404
        with org_context(self.org):
            found = WrittenRecord.objects.filter(
                access=self.access, kind=kind, external_id=external_id
            ).first()
        if found is None:
            raise Http404
        data = {"kind": kind, "id": str(found.object_id), "external_id": external_id}
        return Response(PartnerExternalIdSerializer(data).data)


# --- Termine ---


class PartnerEventInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True)
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField(required=False)
    all_day = serializers.BooleanField(required=False)
    location = serializers.CharField(required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    visibility = serializers.ChoiceField(
        choices=["public", "members"], required=False, help_text="Vorgabe: members"
    )
    unit = serializers.UUIDField(
        required=False, allow_null=True, help_text="Untereinheit, sonst die Einheit des Zugangs"
    )
    is_cancelled = serializers.BooleanField(required=False, help_text="abgesagt")
    cancel_note = serializers.CharField(required=False, allow_blank=True)
    external_id = serializers.CharField(**EXTERNAL_ID)


class PartnerOwnEventSerializer(serializers.Serializer):
    id = serializers.CharField(help_text="wie ``event_id`` unter /events/")
    external_id = serializers.CharField(allow_blank=True)
    title = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    all_day = serializers.BooleanField()
    location = serializers.CharField(allow_blank=True)
    address = serializers.CharField(allow_blank=True)
    visibility = serializers.CharField()
    unit = serializers.UUIDField(allow_null=True)
    is_cancelled = serializers.BooleanField()
    cancel_note = serializers.CharField(allow_blank=True)
    updated_at = serializers.DateTimeField()


EVENT_FIELDS = (
    "title",
    "description",
    "starts_at",
    "ends_at",
    "all_day",
    "location",
    "address",
    "visibility",
    "is_cancelled",
    "cancel_note",
)


def _event_out(event, external_id: str) -> dict:
    data = {
        "id": str(event.pk),
        "external_id": external_id,
        "title": event.title,
        "description": event.description,
        "starts_at": event.starts_at,
        "ends_at": event.ends_at,
        "all_day": event.all_day,
        "location": event.location,
        "address": event.address,
        "visibility": event.visibility,
        "unit": event.department.uuid if event.department_id else None,
        "is_cancelled": event.is_cancelled,
        "cancel_note": event.cancel_note,
        "updated_at": event.updated_at,
    }
    return PartnerOwnEventSerializer(data).data


class EventsView(WriteMixin, base.EventsView):
    """GET wie in Stufe 1; POST legt einen einzelnen Termin an."""

    write_scope = sc.EVENTS_WRITE

    @extend_schema(
        operation_id="event_create",
        summary="Termin anlegen",
        description=(
            "Legt einen einzelnen Termin an (keine Serien, keine Zu- und Absagen, kein "
            "Versand von Einladungen). Mit einer schon benutzten ``external_id`` kommt 409 "
            "mit der Kennung des vorhandenen Termins." + IDEMPOTENCY_NOTE
        ),
        request=PartnerEventInputSerializer,
        responses={201: PartnerOwnEventSerializer, **WRITE_ERRORS},
    )
    def post(self, request):
        from events.serializers import EventWriteSerializer

        def action():
            ser = PartnerEventInputSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            data = dict(ser.validated_data)
            external_id = data.pop("external_id", "")
            check_external(self.access, EVENT, external_id)
            department = self.chosen_unit(data.pop("unit", None))
            write = EventWriteSerializer(
                data={k: data[k] for k in EVENT_FIELDS if k in data},
                context={"org": self.org, "department": department},
            )
            write.is_valid(raise_exception=True)
            event = write.save(organization=self.org, department=department, created_by=None)
            record(self.org, None, "create", event, diff({}, snapshot(event)))
            remember(self.access, EVENT, event.pk, external_id)
            return 201, _event_out(event, external_id)

        return self.run(request, action)


class EventView(WriteMixin, PartnerView):
    scope = sc.EVENTS_WRITE

    def own(self, event_id: str):
        from events.models import Event

        mark = written(self.access, EVENT, event_id)
        event = (
            Event.objects.filter(organization=self.org, pk=mark.object_id)
            .select_related("department")
            .first()
            if mark
            else None
        )
        if event is None or not self.in_reach(event.department_id):
            raise Http404
        return event, mark

    @extend_schema(
        operation_id="event_own",
        summary="Selbst angelegter Termin",
        description="Ein Termin, den dieser Zugang angelegt hat; sonst 404.",
        responses={200: PartnerOwnEventSerializer, 404: PartnerProblemSerializer, **ERRORS},
    )
    def get(self, request, event_id: str):
        with org_context(self.org):
            event, mark = self.own(event_id)
            return Response(_event_out(event, mark.external_id))

    @extend_schema(
        operation_id="event_update",
        summary="Termin ändern oder absagen",
        description=(
            "Ändert einen Termin, den dieser Zugang angelegt hat; nur die gesendeten Felder. "
            "Absagen mit ``is_cancelled``; gelöscht wird nie. 409, wenn der Termin in HUBIplan "
            "zur Serie oder „nur Vorstand“ wurde." + IDEMPOTENCY_NOTE
        ),
        request=PartnerEventInputSerializer,
        responses={
            200: PartnerOwnEventSerializer,
            404: PartnerProblemSerializer,
            **WRITE_ERRORS,
        },
    )
    def patch(self, request, event_id: str):
        from events.models import Event
        from events.serializers import EventWriteSerializer

        def action():
            event, mark = self.own(event_id)
            if event.visibility == Event.Visibility.BOARD or event.repeat != Event.Repeat.NONE:
                raise Problem(
                    409,
                    "record_locked",
                    _("Der Termin wurde in HUBIplan so geändert, dass die API ihn nicht ändert"),
                )
            ser = PartnerEventInputSerializer(data=request.data, partial=True)
            ser.is_valid(raise_exception=True)
            data = dict(ser.validated_data)
            data.pop("external_id", None)
            department = self.chosen_unit(data.pop("unit")) if "unit" in data else event.department
            before = snapshot(event)
            moved_from = (event.starts_at, event.ends_at, event.all_day, event.location)
            was_cancelled, old_start = event.is_cancelled, event.starts_at
            write = EventWriteSerializer(
                event,
                data={k: data[k] for k in EVENT_FIELDS if k in data},
                partial=True,
                context={"org": self.org, "department": department},
            )
            write.is_valid(raise_exception=True)
            event = write.save(department=department)
            fields = []
            if moved_from != (event.starts_at, event.ends_at, event.all_day, event.location):
                event.changed_at = timezone.now()
                fields.append("changed_at")
            if event.starts_at != old_start and event.reminded_at:
                event.reminded_at = None
                fields.append("reminded_at")
            if fields:
                event.save(update_fields=fields)
            if event.starts_at != old_start:
                from competitions.event_views import follow_event

                follow_event(None, event)
            if event.is_cancelled and not was_cancelled:
                from registrations.services import event_cancelled

                event_cancelled(event, None)
            changes = diff(before, snapshot(event))
            if changes:
                record(self.org, None, "update", event, changes)
            return 200, _event_out(event, mark.external_id)

        return self.run(request, action)


# --- Wettbewerbsergebnisse ---


class PartnerEntryScoringSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    unit_label = serializers.CharField(allow_blank=True)
    decimals = serializers.IntegerField()
    higher_better = serializers.BooleanField()


class PartnerEntryCompetitionSerializer(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField()
    date = serializers.DateField()
    status = serializers.CharField()
    scorings = PartnerEntryScoringSerializer(many=True)


class PartnerEntryListSerializer(serializers.Serializer):
    competitions = PartnerEntryCompetitionSerializer(many=True)


class PartnerResultInputSerializer(serializers.Serializer):
    scoring = serializers.CharField(help_text="Kennung der Einzelwertung")
    value = serializers.CharField(allow_blank=True, help_text="Wert als Zahl; leer löscht ihn")
    member = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Kennung des Mitglieds wie unter /members/ (braucht mitglieder.lesen)",
    )
    name = serializers.CharField(required=False, allow_blank=True, help_text="Gast: Name")
    club = serializers.CharField(required=False, allow_blank=True, help_text="Gast: Verein")
    adult = serializers.BooleanField(required=False, help_text="Gast ist volljährig")
    external_id = serializers.CharField(
        max_length=80,
        required=False,
        allow_blank=True,
        help_text="eigene Kennung des Gastes; ohne sie zählen Name und Verein",
    )


class PartnerResultsInputSerializer(serializers.Serializer):
    results = PartnerResultInputSerializer(many=True)


class PartnerResultRejectedSerializer(serializers.Serializer):
    index = serializers.IntegerField(help_text="Stelle in ``results``, ab 0")
    error = serializers.CharField()


class PartnerResultsOutSerializer(serializers.Serializer):
    accepted = serializers.IntegerField()
    rejected = PartnerResultRejectedSerializer(many=True)


def _open_competitions(org):
    from competitions.models import Competition

    return Competition.objects.filter(
        organization=org, own=True, form=Competition.Form.RANKING
    ).exclude(status=Competition.Status.FINAL)


def _message(exc) -> str:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict):
        detail = next(iter(detail.values()), "")
    if isinstance(detail, (list, tuple)):
        detail = detail[0] if detail else ""
    return str(detail or exc)


class ResultEntryView(PartnerView):
    scope = sc.RESULTS_WRITE

    @extend_schema(
        operation_id="result_entry",
        summary="Wettbewerbe, die Ergebnisse annehmen",
        description=(
            "Eigene Wettbewerbe mit Rangliste, die noch nicht endgültig abgeschlossen sind, mit "
            "ihren Einzelwertungen. Keine Starter und keine Namen."
        ),
        responses={200: PartnerEntryListSerializer, **ERRORS},
    )
    def get(self, request):
        from competitions.models import Scoring

        with org_context(self.org):
            rows = []
            for comp in _open_competitions(self.org).order_by("date", "pk")[:200]:
                scorings = comp.scorings.filter(kind=Scoring.Kind.INDIVIDUAL).order_by(
                    "sort_order", "pk"
                )
                rows.append(
                    {
                        "id": str(comp.pk),
                        "title": comp.title,
                        "date": comp.date,
                        "status": comp.status,
                        "scorings": [
                            {
                                "id": str(s.pk),
                                "name": s.name,
                                "unit_label": s.unit_label,
                                "decimals": s.decimals,
                                "higher_better": s.higher_better,
                            }
                            for s in scorings
                        ],
                    }
                )
        return Response(PartnerEntryListSerializer({"competitions": rows}).data)


class ResultsWriteView(WriteMixin, PartnerView):
    scope = sc.RESULTS_WRITE

    @extend_schema(
        operation_id="results_deliver",
        summary="Ergebnisse einliefern",
        description=(
            "Trägt Werte in Einzelwertungen eines laufenden Wettbewerbs ein, höchstens 500 je "
            "Anfrage. Starter ist ein Mitglied (``member``) oder ein Gast (``name``, ``club``); "
            "fehlende Starter werden angelegt. Jede Zeile wird einzeln geprüft: Abgelehnte "
            "stehen mit Grund in ``rejected``, die übrigen gelten." + IDEMPOTENCY_NOTE
        ),
        request=PartnerResultsInputSerializer,
        responses={
            200: PartnerResultsOutSerializer,
            404: PartnerProblemSerializer,
            **WRITE_ERRORS,
        },
    )
    def post(self, request, competition_id: str):
        from competitions.models import Scoring
        from competitions.views import create_starter, set_score

        def action():
            ser = PartnerResultsInputSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            rows = ser.validated_data["results"]
            if len(rows) > MAX_RESULTS:
                raise ValidationError(
                    {"results": _("Höchstens {n} Ergebnisse je Anfrage.").format(n=MAX_RESULTS)}
                )
            comp = (
                _open_competitions(self.org).filter(pk=competition_id).first()
                if str(competition_id).isdigit()
                else None
            )
            if comp is None:
                raise Http404
            scorings = {str(s.pk): s for s in comp.scorings.filter(kind=Scoring.Kind.INDIVIDUAL)}
            members_ok = sc.MEMBERS_READ in self.granted(self.access) and self.access.personal_ok
            starters = list(comp.starters.all())
            by_member = {s.membership_id: s for s in starters if s.membership_id}
            guests = {
                (s.name.strip().lower(), s.club.strip().lower()): s
                for s in starters
                if not s.membership_id
            }
            by_external = {
                w.external_id: w.object_id
                for w in WrittenRecord.objects.filter(access=self.access, kind=STARTER).exclude(
                    external_id=""
                )
            }
            by_pk = {s.pk: s for s in starters}
            accepted, rejected = 0, []
            for index, row in enumerate(rows):
                try:
                    with transaction.atomic():
                        scoring = scorings.get(str(row["scoring"]))
                        if scoring is None:
                            raise ValidationError(_("Unbekannte Wertung."))
                        made, member_pk, guest, external_id = False, None, None, ""
                        starter = None
                        if row.get("member"):
                            if members_ok:
                                member_pk = refs.resolve(self.org, refs.MEMBER, row["member"])
                            if member_pk is None:
                                raise ValidationError(_("Unbekanntes Mitglied."))
                            starter = by_member.get(member_pk)
                            if starter is None:
                                starter = create_starter(
                                    self.org, None, comp, {"membership": member_pk}
                                )
                                made = True
                        else:
                            name = (row.get("name") or "").strip()
                            club = (row.get("club") or "").strip()
                            guest = (name.lower(), club.lower())
                            if row.get("external_id"):
                                # je Wettbewerb eindeutig
                                external_id = f"{comp.pk}:{row['external_id']}"
                                starter = by_pk.get(by_external.get(external_id))
                            if starter is None:
                                starter = guests.get(guest)
                            if starter is None:
                                starter = create_starter(
                                    self.org,
                                    None,
                                    comp,
                                    {"name": name, "club": club, "adult": row.get("adult", False)},
                                )
                                made = True
                                if external_id:
                                    remember(self.access, STARTER, starter.pk, external_id)
                        set_score(self.org, None, comp, scoring, starter, row["value"])
                    accepted += 1
                    if made:
                        # Erst merken, wenn die Zeile gilt (sonst ist der Starter verworfen)
                        by_pk[starter.pk] = starter
                        if member_pk is not None:
                            by_member[member_pk] = starter
                        else:
                            guests[guest] = starter
                            if external_id:
                                by_external[external_id] = starter.pk
                except ValidationError as exc:
                    rejected.append({"index": index, "error": _message(exc)})
            out = {"accepted": accepted, "rejected": rejected}
            return 200, PartnerResultsOutSerializer(out).data

        return self.run(request, action)


# --- Training und Anwesenheit ---


class PartnerTrainingInputSerializer(serializers.Serializer):
    date = serializers.DateField()
    title = serializers.CharField(max_length=200)
    starts_at = serializers.TimeField(required=False, allow_null=True)
    ends_at = serializers.TimeField(required=False, allow_null=True)
    kind = serializers.ChoiceField(
        choices=["practice", "training", "competition", "other"], required=False
    )
    location = serializers.CharField(required=False, allow_blank=True, max_length=200)
    leader = serializers.CharField(required=False, allow_blank=True, max_length=200)
    unit = serializers.UUIDField(required=False, allow_null=True)
    external_id = serializers.CharField(**EXTERNAL_ID)


class PartnerTrainingSerializer(serializers.Serializer):
    id = serializers.CharField()
    external_id = serializers.CharField(allow_blank=True)
    date = serializers.DateField()
    title = serializers.CharField()
    starts_at = serializers.TimeField(allow_null=True)
    ends_at = serializers.TimeField(allow_null=True)
    kind = serializers.CharField()
    location = serializers.CharField(allow_blank=True)
    leader = serializers.CharField(allow_blank=True)
    unit = serializers.UUIDField(allow_null=True)
    present = serializers.ListField(
        child=serializers.UUIDField(), help_text="Kennungen der Anwesenden wie unter /members/"
    )


class PartnerAttendanceInputSerializer(serializers.Serializer):
    present = serializers.ListField(child=serializers.UUIDField(), required=False)
    absent = serializers.ListField(child=serializers.UUIDField(), required=False)


class PartnerAttendanceOutSerializer(serializers.Serializer):
    changed = serializers.IntegerField(help_text="geänderte Einträge")
    unknown = serializers.ListField(
        child=serializers.UUIDField(),
        help_text="Kennungen, die der Zugang nicht sieht oder die nicht zur Einheit gehören",
    )
    present = serializers.ListField(child=serializers.UUIDField())


def _present(session) -> list:
    ids = list(session.attendances.order_by("pk").values_list("membership_id", flat=True))
    known = refs.public_ids(session.organization, refs.MEMBER, ids)
    return [known[i] for i in ids if i in known]


def _training_out(session, external_id: str) -> dict:
    data = {
        "id": str(session.pk),
        "external_id": external_id,
        "date": session.date,
        "title": session.title,
        "starts_at": session.starts_at,
        "ends_at": session.ends_at,
        "kind": session.kind,
        "location": session.location,
        "leader": session.leader,
        "unit": session.department.uuid if session.department_id else None,
        "present": _present(session),
    }
    return PartnerTrainingSerializer(data).data


class TrainingsView(WriteMixin, PersonalView):
    scope = sc.ATTENDANCE_WRITE

    @extend_schema(
        operation_id="training_create",
        summary="Trainingstermin anlegen",
        description=(
            "Legt einen Trainingstermin für die Anwesenheit an (kein Schießtermin, kein "
            "Eintrag im Schießbuch)." + IDEMPOTENCY_NOTE
        ),
        request=PartnerTrainingInputSerializer,
        responses={201: PartnerTrainingSerializer, **WRITE_ERRORS},
    )
    def post(self, request):
        from training.services import create_session

        def action():
            ser = PartnerTrainingInputSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            data = dict(ser.validated_data)
            external_id = data.pop("external_id", "")
            check_external(self.access, TRAINING, external_id)
            department = self.chosen_unit(data.pop("unit", None))
            fields = {
                k: (v.isoformat() if hasattr(v, "isoformat") else v)
                for k, v in data.items()
                if v is not None
            }
            session = create_session(self.org, department, None, fields)
            remember(self.access, TRAINING, session.pk, external_id)
            return 201, _training_out(session, external_id)

        return self.run(request, action)


class _OwnTraining(WriteMixin, PersonalView):
    scope = sc.ATTENDANCE_WRITE

    def own(self, training_id: str):
        from training.models import TrainingSession

        mark = written(self.access, TRAINING, training_id)
        session = (
            TrainingSession.objects.filter(organization=self.org, pk=mark.object_id)
            .select_related("department")
            .first()
            if mark
            else None
        )
        if session is None or not self.in_reach(session.department_id):
            raise Http404
        return session, mark


class TrainingView(_OwnTraining):
    @extend_schema(
        operation_id="training_own",
        summary="Selbst angelegter Trainingstermin",
        description="Ein Trainingstermin dieses Zugangs mit den Anwesenden; sonst 404.",
        responses={200: PartnerTrainingSerializer, 404: PartnerProblemSerializer, **ERRORS},
    )
    def get(self, request, training_id: str):
        with org_context(self.org):
            session, mark = self.own(training_id)
            data = _training_out(session, mark.external_id)
            log_read(self.access, self.scope, len(data["present"]))
        return Response(data)


class AttendanceView(_OwnTraining):
    @extend_schema(
        operation_id="attendance_set",
        summary="Anwesenheit eintragen",
        description=(
            "Trägt Mitglieder als anwesend ein (``present``) oder wieder aus (``absent``), "
            "höchstens 1000 je Anfrage; nur bei einem Trainingstermin dieses Zugangs. Wer nicht "
            "genannt ist, bleibt, wie er ist." + IDEMPOTENCY_NOTE
        ),
        request=PartnerAttendanceInputSerializer,
        responses={
            200: PartnerAttendanceOutSerializer,
            404: PartnerProblemSerializer,
            **WRITE_ERRORS,
        },
    )
    def post(self, request, training_id: str):
        from training.services import candidates, set_present

        def action():
            ser = PartnerAttendanceInputSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            present = list(dict.fromkeys(ser.validated_data.get("present") or []))
            absent = list(dict.fromkeys(ser.validated_data.get("absent") or []))
            if len(present) + len(absent) > MAX_ATTENDANCE:
                raise ValidationError(
                    _("Höchstens {n} Einträge je Anfrage.").format(n=MAX_ATTENDANCE)
                )
            session, _mark = self.own(training_id)
            visible = {m.pk: m for m in self.memberships(request, status="all")}
            allowed = set(candidates(session).values_list("pk", flat=True)) & set(visible)
            changed, unknown = 0, []
            for ids, flag in ((present, True), (absent, False)):
                for public_id in ids:
                    pk = refs.resolve(self.org, refs.MEMBER, public_id)
                    if pk not in allowed:
                        unknown.append(public_id)
                        continue
                    changed += bool(set_present(session, visible[pk], flag, None))
            out = {"changed": changed, "unknown": unknown, "present": _present(session)}
            return 200, PartnerAttendanceOutSerializer(out).data

        return self.run(request, action)


# --- Mitglieder: Änderungen als Vorschlag ---


class PartnerProposalInputSerializer(serializers.Serializer):
    last_name = serializers.CharField(max_length=100, required=False)
    first_name = serializers.CharField(max_length=100, required=False)
    birth_date = serializers.DateField(required=False)
    email = serializers.EmailField(required=False)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=50)
    street = serializers.CharField(max_length=200, required=False)
    postal_code = serializers.CharField(max_length=10, required=False)
    city = serializers.CharField(max_length=100, required=False)
    country = serializers.CharField(max_length=100, required=False)
    message = serializers.CharField(
        max_length=300, required=False, allow_blank=True, help_text="Hinweis für den Verein"
    )
    external_id = serializers.CharField(**EXTERNAL_ID)


class PartnerProposalSerializer(serializers.Serializer):
    id = serializers.CharField()
    external_id = serializers.CharField(allow_blank=True)
    member = serializers.UUIDField()
    status = serializers.CharField(help_text="pending, accepted oder rejected")
    changed = serializers.ListField(
        child=serializers.CharField(), help_text="vorgeschlagene Felder"
    )
    created_at = serializers.DateTimeField()
    decided_at = serializers.DateTimeField(allow_null=True)


PROPOSAL_FIELDS = (
    "last_name",
    "first_name",
    "birth_date",
    "email",
    "phone",
    "street",
    "postal_code",
    "city",
    "country",
)


def proposal_prefix(access: ApiAccess) -> str:
    return f"Vorschlag über den API-Zugang {access.name}"


def _proposal_out(cr, external_id: str) -> dict:
    member = refs.public_ids(cr.organization, refs.MEMBER, [cr.membership_id])
    data = {
        "id": str(cr.pk),
        "external_id": external_id,
        "member": member[cr.membership_id],
        "status": cr.status,
        "changed": sorted(cr.data or {}),
        "created_at": cr.created_at,
        "decided_at": cr.decided_at,
    }
    return PartnerProposalSerializer(data).data


class MemberProposalsView(WriteMixin, PersonalView):
    scope = sc.MEMBERS_WRITE

    @extend_schema(
        operation_id="member_proposal_create",
        summary="Änderung an einem Mitglied vorschlagen",
        description=(
            "Reicht geänderte Namen oder Kontaktdaten als Vorschlag ein. Es ändert sich nichts, "
            "bis jemand im Verein den Vorschlag übernimmt. Nur Felder, die sich vom heutigen "
            "Stand unterscheiden, werden vorgeschlagen; höchstens drei offene Vorschläge je "
            "Mitglied." + IDEMPOTENCY_NOTE
        ),
        request=PartnerProposalInputSerializer,
        responses={
            201: PartnerProposalSerializer,
            404: PartnerProblemSerializer,
            **WRITE_ERRORS,
        },
    )
    def post(self, request, member_id: str):
        from portal.models import ChangeRequest
        from portal.views import current_values

        def action():
            ser = PartnerProposalInputSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            values = dict(ser.validated_data)
            message = values.pop("message", "").strip()
            external_id = values.pop("external_id", "")
            check_external(self.access, PROPOSAL, external_id)
            pk = refs.resolve(self.org, refs.MEMBER, member_id)
            membership = next(
                (m for m in self.memberships(request, status="all") if m.pk == pk), None
            )
            if membership is None:
                raise Http404
            if membership.person.is_organization:
                for key in ("first_name", "birth_date"):
                    values.pop(key, None)
            previous = current_values(self.org, membership)
            changed = {}
            for key in PROPOSAL_FIELDS:
                if key not in values:
                    continue
                value = values[key]
                value = value.isoformat() if hasattr(value, "isoformat") else value.strip()
                if value != (previous.get(key) or ""):
                    changed[key] = value
            if not changed:
                raise ValidationError(_("Die Angaben entsprechen dem heutigen Stand."))
            prefix = proposal_prefix(self.access)
            pending = ChangeRequest.objects.filter(
                organization=self.org,
                user=None,
                status=ChangeRequest.Status.PENDING,
                message__startswith=prefix,
            )
            if (
                pending.filter(membership=membership).count() >= MAX_OPEN_PER_MEMBER
                or pending.count() >= MAX_OPEN_PER_ACCESS
            ):
                raise Problem(
                    409,
                    "too_many_open",
                    _("Zu viele offene Vorschläge; der Verein muss erst welche bearbeiten"),
                )
            cr = ChangeRequest.objects.create(
                organization=self.org,
                membership=membership,
                user=None,
                data=changed,
                previous={k: previous.get(k) for k in changed},
                message=(prefix + (f": {message}" if message else ""))[:500],
            )
            record(
                self.org,
                None,
                "create",
                cr,
                {k: [previous.get(k), v] for k, v in changed.items()},
                person=membership.person,
            )
            remember(self.access, PROPOSAL, cr.pk, external_id)
            return 201, _proposal_out(cr, external_id)

        return self.run(request, action)


class ProposalView(PersonalView):
    scope = sc.MEMBERS_WRITE

    @extend_schema(
        operation_id="member_proposal",
        summary="Stand eines Vorschlags",
        description="Ob der Verein den Vorschlag dieses Zugangs übernommen oder abgelehnt hat.",
        responses={200: PartnerProposalSerializer, 404: PartnerProblemSerializer, **ERRORS},
    )
    def get(self, request, proposal_id: str):
        from portal.models import ChangeRequest

        with org_context(self.org):
            mark = written(self.access, PROPOSAL, proposal_id)
            cr = (
                ChangeRequest.objects.filter(organization=self.org, pk=mark.object_id).first()
                if mark
                else None
            )
            if cr is None:
                raise Http404
            return Response(_proposal_out(cr, mark.external_id))


# --- Ausweis prüfen ---


class PartnerCardInputSerializer(serializers.Serializer):
    code = serializers.CharField(
        max_length=500, help_text="Inhalt des QR-Codes: die Prüfadresse oder ihr letzter Teil"
    )


class PartnerCardSerializer(serializers.Serializer):
    valid = serializers.BooleanField(help_text="Ausweis der Einheit mit gültiger Mitgliedschaft")
    status = serializers.CharField(help_text="active, future, inactive oder unknown")
    member_type = serializers.CharField(allow_null=True, help_text="Art der Mitgliedschaft")


def _card_state(membership) -> dict:
    """Wie die Prüfseite des Ausweises, nur ohne Namen: gültig, später gültig oder nicht."""
    from members.models import MembershipPeriod

    on = timezone.localdate()
    status, member_type = "inactive", None
    if membership.current_period(on):
        status = "active"
        current = membership.current_type(on)
        member_type = current.member_type.name if current else None
    elif MembershipPeriod.objects.filter(membership=membership, entry_date__gt=on).exists():
        status = "future"
    return {"valid": status == "active", "status": status, "member_type": member_type}


class CardCheckView(PersonalView):
    scope = sc.CARD_CHECK
    writes = False

    @extend_schema(
        operation_id="card_check",
        summary="Mitgliedsausweis prüfen",
        description=(
            "Prüft den Code eines Mitgliedsausweises der Einheit, zum Beispiel am Einlass. "
            "Zurück kommen nur gültig oder nicht und die Art der Mitgliedschaft, nie Name, "
            "Foto oder Nummer. Fremde, gesperrte und unbekannte Ausweise: ``unknown``."
        ),
        request=PartnerCardInputSerializer,
        responses={200: PartnerCardSerializer, 400: PartnerProblemSerializer, **ERRORS},
    )
    def post(self, request):
        from cards.services import find_valid

        ser = PartnerCardInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        token = ser.validated_data["code"].strip().rstrip("/").rsplit("/", 1)[-1]
        token = token.split("?", 1)[0]
        card = find_valid(token)
        data = {"valid": False, "status": "unknown", "member_type": None}
        if card is not None and card.organization_id == self.org.pk:
            with org_context(self.org):
                data = _card_state(card.membership)
                log_read(self.access, self.scope, 1)
        return Response(PartnerCardSerializer(data).data)


# --- Rundschreiben als Entwurf ---


class PartnerCircularInputSerializer(serializers.Serializer):
    subject = serializers.CharField(max_length=200)
    body = serializers.CharField(
        help_text="Text mit einfacher Auszeichnung: **fett**, *kursiv*, Listen mit „- “"
    )
    external_id = serializers.CharField(**EXTERNAL_ID)


class PartnerCircularSerializer(serializers.Serializer):
    id = serializers.CharField()
    external_id = serializers.CharField(allow_blank=True)
    subject = serializers.CharField()
    status = serializers.CharField(help_text="draft, sending oder sent")
    created_at = serializers.DateTimeField()


class CircularDraftsView(WriteMixin, PartnerView):
    scope = sc.CIRCULARS_WRITE

    @extend_schema(
        operation_id="circular_draft_create",
        summary="Rundschreiben als Entwurf einliefern",
        description=(
            "Legt Betreff und Text als Entwurf unter Rundschreiben ab. Empfänger wählt und "
            "versendet ein Mensch in HUBIplan; die API versendet nie. Höchstens 20 Entwürfe "
            "dieses Zugangs zugleich." + IDEMPOTENCY_NOTE
        ),
        request=PartnerCircularInputSerializer,
        responses={201: PartnerCircularSerializer, **WRITE_ERRORS},
    )
    def post(self, request):
        from circulars.models import Circular
        from circulars.views import CircularWriteSerializer

        def action():
            ser = PartnerCircularInputSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            data = dict(ser.validated_data)
            external_id = data.pop("external_id", "")
            check_external(self.access, CIRCULAR, external_id)
            mine = WrittenRecord.objects.filter(access=self.access, kind=CIRCULAR).values_list(
                "object_id", flat=True
            )
            drafts = Circular.objects.filter(
                organization=self.org, pk__in=list(mine), status=Circular.Status.DRAFT
            ).count()
            if drafts >= MAX_DRAFTS:
                raise Problem(
                    409,
                    "too_many_open",
                    _("Zu viele Entwürfe; der Verein muss erst welche versenden oder löschen"),
                )
            payload = {"kind": Circular.Kind.INFO, **data}
            if self.org.type == "federation":
                payload["audience"] = Circular.Audience.BOARDS
            write = CircularWriteSerializer(data=payload, context={"org": self.org, "dept": None})
            write.is_valid(raise_exception=True)
            circular = write.save(
                organization=self.org, department=None, created_by=None, reply_to=""
            )
            record(self.org, None, "create", circular, {"Betreff": [None, circular.subject]})
            remember(self.access, CIRCULAR, circular.pk, external_id)
            out = {
                "id": str(circular.pk),
                "external_id": external_id,
                "subject": circular.subject,
                "status": circular.status,
                "created_at": circular.created_at,
            }
            return 201, PartnerCircularSerializer(out).data

        return self.run(request, action)
