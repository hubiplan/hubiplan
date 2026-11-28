"""Wettbewerbe in der Verwaltung (Menü „Wettbewerbe“).

Rechte: „Wettbewerbe verwalten“ richtet ein (Grunddaten, Wertungen, Zustand, Löschen);
„Ergebnisse erfassen“ trägt Starter, Werte und Stechen ein und sieht von Startern nur
Name, Untereinheit und Startnummer. Lesen darf, wer eines der beiden Rechte hat.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, F, Max, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers, status, viewsets
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from access.catalog import (
    COMPETITIONS_MANAGE,
    COMPETITIONS_RESULTS,
    COMPETITIONS_VIEW,
    RESULTS_VIEW,
)
from access.modules import module_on
from audit.log import diff, record, snapshot
from core.api_base import AuditMixin, OrgScopedMixin
from core.webslug import take_from_attrs
from members.models import Membership
from members.personsearch import filter_names, ordered
from organizations.models import Department, Organization

from . import awards, bird, report, services
from .models import (
    Award,
    Competition,
    Hit,
    Placing,
    Prize,
    Score,
    Scoring,
    ShootOff,
    Starter,
    Team,
)
from .shootoffs import (
    create_shootoff,
    delete_shootoff,
    list_shootoffs,
    update_shootoff,
    update_shootoff_entry,
)
from .starters import (
    _person_name,
    _starter_data,
    _starters_with_values,
    _umlaut_variants,
    _units,
    create_starter,
    delete_starter,
    set_score,
    unit_members,
    update_starter,
)
from .sync import _jsonable, sync

MODULE = "competitions"


class _Mixin(OrgScopedMixin):
    """Lesen mit einem der beiden Rechte; Schreiben je Ansicht (``manage_only``)."""

    allowed_org_types = (Organization.Type.CLUB, Organization.Type.FEDERATION)
    manage_only = True

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if MODULE not in (self.org.enabled_modules or []):
            raise NotFound(gettext("Das Modul Wettbewerbe ist nicht freigeschaltet."))
        perms = self.org_permissions
        # Lesen: Wettbewerbe oder Ergebnisse lesen; Ändern: Wettbewerbe bearbeiten bzw.
        # bei Ergebnissen auch Ergebnisse bearbeiten (konzepte/berechtigungen.md)
        readable = {COMPETITIONS_VIEW, RESULTS_VIEW, COMPETITIONS_MANAGE, COMPETITIONS_RESULTS}
        if not (readable & perms):
            raise PermissionDenied(gettext("Dafür fehlt dir die Berechtigung."))
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if self.manage_only and COMPETITIONS_MANAGE not in perms:
                raise PermissionDenied(gettext("Dafür fehlt dir die Berechtigung."))
            if not ({COMPETITIONS_MANAGE, COMPETITIONS_RESULTS} & perms):
                raise PermissionDenied(gettext("Dafür fehlt dir die Berechtigung."))

    @property
    def can_manage(self) -> bool:
        return COMPETITIONS_MANAGE in self.org_permissions

    def competition(self, pk) -> Competition:
        return get_object_or_404(Competition, pk=pk, organization=self.org)


# --- Wettbewerbe ---


def _from_internal_call(comp: Competition) -> bool:
    """Gehört der Wettbewerb zu einer Ausschreibung an Untereinheiten?"""
    from entries.models import Call

    return Call.objects.filter(competition=comp, internal=True).exists()


class CompetitionSerializer(serializers.ModelSerializer):
    starter_count = serializers.IntegerField(read_only=True, default=0)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    event = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Competition
        fields = [
            "id",
            "title",
            "form",
            "own",
            "organizer",
            "occasion",
            "discipline",
            "location",
            "date",
            "description",
            "details",
            "status",
            "status_label",
            "generation",
            "website",
            "website_depth",
            "share_ranking",
            "certificate_template",
            "series",
            "drop_out",
            "fixed_order",
            "total_shots",
            "lots",
            "event",
            "starter_count",
            # Webseite #149: Adresse auf der Webseite; leer = aus dem Titel und Jahr
            "web_slug",
            "web_slug_auto",
        ]
        read_only_fields = ["status", "generation", "web_slug_auto"]
        extra_kwargs = {"web_slug": {"required": False, "allow_blank": True, "max_length": 80}}

    def validate(self, attrs):
        take_from_attrs(
            attrs,
            self.instance,
            Competition.objects.filter(organization=self.context.get("org")),
        )
        if self.instance is not None:
            for field in ("form", "own"):
                if field in attrs and attrs[field] != getattr(self.instance, field):
                    raise serializers.ValidationError(
                        {field: gettext("Die Art des Wettbewerbs lässt sich nicht mehr ändern.")}
                    )
        form = attrs.get("form", getattr(self.instance, "form", Competition.Form.RANKING))
        own = attrs.get("own", getattr(self.instance, "own", True))
        org = self.context.get("org")
        if (
            self.instance is None
            and form == Competition.Form.BIRD
            and not module_on(org, "shooting")
        ):
            raise serializers.ValidationError(
                {"form": gettext("Ein Vogelschießen gibt es nur mit dem Modul „Schießsport“.")}
            )
        if form == Competition.Form.BIRD and not own:
            raise serializers.ValidationError(
                {"own": gettext("Ein Vogelschießen lässt sich nur als eigener Wettbewerb anlegen.")}
            )
        return attrs

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError(gettext("Bitte einen Titel angeben."))
        return value

    def validate_series(self, value):
        org = self.context.get("org")
        if value is not None and (org is None or value.organization_id != org.pk):
            raise serializers.ValidationError(gettext("Bitte eine Reihe dieser Einheit wählen."))
        return value

    def validate_certificate_template(self, value):
        org = self.context.get("org")
        if value is not None and (org is None or value.organization_id != org.pk):
            raise serializers.ValidationError(gettext("Bitte eine Vorlage dieser Einheit wählen."))
        return value

    def validate_details(self, value):
        if not isinstance(value, list) or len(value) > 30:
            raise serializers.ValidationError(gettext("Höchstens 30 weitere Angaben."))
        out = []
        for item in value:
            if not isinstance(item, dict):
                raise serializers.ValidationError(gettext("Ungültige Angabe."))
            label = str(item.get("label", "")).strip()[:60]
            text = str(item.get("value", "")).strip()[:200]
            if label or text:
                out.append({"label": label, "value": text})
        return out


class ScoringSerializer(serializers.ModelSerializer):
    # Aufgelöste Scheibe (Maße, Ringe) zum Zeichnen und Rechnen am Stand, auch offline
    target_info = serializers.SerializerMethodField()
    confirm_recalculation = serializers.BooleanField(write_only=True, required=False)
    has_results = serializers.SerializerMethodField()

    class Meta:
        model = Scoring
        fields = [
            "id",
            "competition",
            "program",
            "name",
            "kind",
            "sort_order",
            "shots",
            "counted_shots",
            "max_per_shot",
            "unit_label",
            "decimals",
            "higher_better",
            "source",
            "team_mode",
            "team_size",
            "prize_places",
            "shootoff_shots",
            "shootoff_counted",
            "field_size",
            "target",
            "custom_target",
            "method",
            "tie_breaks",
            "series_size",
            "target_info",
            "confirm_recalculation",
            "has_results",
        ]
        read_only_fields = ["competition"]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_target_info(self, obj) -> dict | None:
        target = services.target_of(obj)
        return target.as_dict() if target else None

    def get_has_results(self, obj) -> bool:
        source = obj.source if obj.kind == Scoring.Kind.UNIT else obj
        return bool(source and (source.scores.exists() or services.hits_for(source).exists()))

    def validate_target(self, value):
        from . import targets

        value = (value or "").strip()
        if value and value != targets.CUSTOM and value not in targets.BY_KEY:
            raise serializers.ValidationError(gettext("Unbekannte Scheibe."))
        # Neue Scheiben nur mit dem Modul „Schießsport“; gespeicherte bleiben erhalten
        current = getattr(self.instance, "target", "") if self.instance is not None else ""
        comp = self.context.get("competition")
        if value and value != current and comp and not module_on(comp.organization, "shooting"):
            raise serializers.ValidationError(
                gettext("Schießscheiben gibt es nur mit dem Modul „Schießsport“.")
            )
        return value

    def validate_custom_target(self, value):
        from . import targets

        if value in (None, {}, ""):
            return {}
        try:
            return targets.clean_custom(value)
        except targets.TargetError as exc:
            label = targets.FIELD_LABELS.get(exc.field, "Scheibe")
            raise serializers.ValidationError(
                gettext("{label}: {x1}").format(label=label, x1=exc.message)
            ) from exc

    def validate_tie_breaks(self, value):
        from . import tiebreak

        try:
            return tiebreak.clean(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_series_size(self, value):
        if value < 1 or value > 100:
            raise serializers.ValidationError(gettext("Bitte 1 bis 100 Schüsse je Serie."))
        return value

    def _target_rules(self, attrs, get) -> None:
        """Scheibe und Wertungsart: passende Nachkommastellen, Richtung und Höchstwert."""
        from . import targets

        target_key, method = get("target") or "", get("method") or Scoring.Method.FREE
        if target_key == targets.CUSTOM and not get("custom_target"):
            raise serializers.ValidationError(
                {"custom_target": gettext("Bitte die Maße der eigenen Scheibe angeben.")}
            )
        kind = get("kind") or Scoring.Kind.INDIVIDUAL
        if method != Scoring.Method.FREE and kind != Scoring.Kind.INDIVIDUAL:
            raise serializers.ValidationError(
                {"method": gettext("Ringe, Zehntel oder Teiler gibt es nur in Einzelwertungen.")}
            )
        if method != Scoring.Method.FREE and not target_key:
            raise serializers.ValidationError(
                {"target": gettext("Für Ringe, Zehntel oder Teiler bitte eine Scheibe wählen.")}
            )
        touched = {"target", "custom_target", "method"} & set(attrs)
        if not touched or method == Scoring.Method.FREE:
            return
        target = targets.get(target_key, get("custom_target"))
        if target is None:
            return
        if method == Scoring.Method.RINGS:
            attrs.update(
                decimals=0, higher_better=True, max_per_shot=Decimal(target.top), unit_label="Ringe"
            )
        elif method == Scoring.Method.DECIMAL:
            attrs.update(
                decimals=1,
                higher_better=True,
                max_per_shot=targets.max_decimal(target),
                unit_label="Ringe",
            )
        else:
            attrs.update(decimals=1, higher_better=False, max_per_shot=None, unit_label="Teiler")

    def validate_decimals(self, value):
        if value > 3:
            raise serializers.ValidationError(gettext("Höchstens 3 Nachkommastellen."))
        return value

    def validate(self, attrs):
        comp = self.context["competition"]
        if comp.status == Competition.Status.FINAL:
            raise serializers.ValidationError(
                gettext("Der Wettbewerb ist endgültig abgeschlossen.")
            )
        program = attrs.get("program", getattr(self.instance, "program", None))
        kind = attrs.get("kind", getattr(self.instance, "kind", Scoring.Kind.INDIVIDUAL))
        if program:
            if program.competition_id != comp.pk or kind != Scoring.Kind.INDIVIDUAL or not comp.own:
                raise serializers.ValidationError(
                    {"program": gettext("Bitte einen Schießdurchgang dieses Wettbewerbs wählen.")}
                )
            if "program" in attrs or self.instance is None:
                if (
                    self.instance
                    and self.instance.program_id != program.pk
                    and (self.instance.scores.exists() or services.hits_for(self.instance).exists())
                ):
                    raise serializers.ValidationError(
                        {
                            "program": gettext(
                                "Die Grundlage kann mit vorhandenen Ergebnissen "
                                "nicht gewechselt werden."
                            )
                        }
                    )
                attrs.update(
                    target=program.target, custom_target=program.custom_target, shots=program.shots
                )
                if self.instance is None and program.target and "method" not in attrs:
                    attrs["method"] = Scoring.Method.RINGS
        elif "program" in attrs and comp.own and kind == Scoring.Kind.INDIVIDUAL:
            raise serializers.ValidationError(
                {"program": gettext("Bitte einen Schießdurchgang wählen.")}
            )
        get = lambda name: attrs.get(name, getattr(self.instance, name, None))  # noqa: E731
        name = (get("name") or "").strip()
        if not name:
            raise serializers.ValidationError({"name": gettext("Bitte eine Bezeichnung angeben.")})
        if comp.form == Competition.Form.BIRD:
            raise serializers.ValidationError(
                gettext("Beim Vogelschießen gibt es keine Wertungen, nur Pfänder.")
            )
        kind = get("kind")
        if kind == Scoring.Kind.TEAM and comp.own:
            raise serializers.ValidationError(
                {"kind": gettext("Mannschaftswertungen gibt es nur bei fremden Wettbewerben.")}
            )
        if kind == Scoring.Kind.UNIT and not comp.own:
            raise serializers.ValidationError(
                {"kind": gettext("Bei fremden Wettbewerben: Einzel- oder Mannschaftswertung.")}
            )
        attrs["name"] = name if "name" in attrs or not self.instance else attrs.get("name", name)
        shots, counted = get("shots"), get("counted_shots")
        if shots and counted and counted > shots:
            raise serializers.ValidationError(
                {
                    "counted_shots": gettext(
                        "Es können nicht mehr Schüsse zählen als geschossen werden."
                    )
                }
            )
        so_shots, so_counted = get("shootoff_shots"), get("shootoff_counted")
        if so_shots and so_counted and so_counted > so_shots:
            raise serializers.ValidationError(
                {
                    "shootoff_counted": gettext(
                        "Es können nicht mehr Schüsse zählen als geschossen werden."
                    )
                }
            )
        if get("kind") == Scoring.Kind.UNIT:
            source = get("source")
            if source is None:
                source = (
                    Scoring.objects.filter(competition=comp, kind=Scoring.Kind.INDIVIDUAL)
                    .order_by("sort_order", "pk")
                    .first()
                )
                if source is None:
                    raise serializers.ValidationError(
                        {"source": gettext("Zuerst eine Einzelwertung anlegen.")}
                    )
                attrs["source"] = source
            elif source.competition_id != comp.pk or source.kind != Scoring.Kind.INDIVIDUAL:
                raise serializers.ValidationError(
                    {"source": gettext("Bitte eine Einzelwertung wählen.")}
                )
            if get("team_mode") == Scoring.TeamMode.SUM_BEST and not get("team_size"):
                raise serializers.ValidationError(
                    {"team_size": gettext("Bitte angeben, wie viele der besten zählen.")}
                )
        else:
            attrs["source"] = None
        self._target_rules(attrs, get)
        if self.instance and not self.context.get("program_update"):
            changed = any(
                key in attrs and attrs[key] != getattr(self.instance, key)
                for key in (
                    "target",
                    "custom_target",
                    "method",
                    "shots",
                    "counted_shots",
                    "tie_breaks",
                    "series_size",
                    "higher_better",
                    "decimals",
                    "max_per_shot",
                    "source",
                    "team_mode",
                    "team_size",
                )
            )
            if (
                changed
                and self.get_has_results(self.instance)
                and not attrs.get("confirm_recalculation")
            ):
                raise serializers.ValidationError(
                    {
                        "confirm_recalculation": gettext(
                            "Die Änderung betrifft vorhandene Ergebnisse. "
                            "Bitte die Neuberechnung bestätigen."
                        )
                    }
                )
        return attrs

    def create(self, validated_data):
        validated_data.pop("confirm_recalculation", None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("confirm_recalculation", None)
        return super().update(instance, validated_data)


class CompetitionViewSet(_Mixin, AuditMixin, viewsets.ModelViewSet):
    serializer_class = CompetitionSerializer

    def get_queryset(self):
        return Competition.objects.filter(organization=self.org).annotate(
            starter_count=Count("starters")
        )

    def get_create_kwargs(self) -> dict:
        return {"organization": self.org}

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "org": getattr(self, "org", None)}

    @transaction.atomic
    def perform_create(self, serializer):
        template = self.request.data.get("template")
        if template == "vogel" and not module_on(self.org, "shooting"):
            raise ValidationError(
                {"form": gettext("Ein Vogelschießen gibt es nur mit dem Modul „Schießsport“.")}
            )
        super().perform_create(serializer)
        comp = serializer.instance
        self._calendar(comp)
        if template == "schiessen":
            # Vorlage „Schießen mit Einzel- und Zugwertung“ (Leitszenario des Pilotvereins)
            single = Scoring.objects.create(
                organization=self.org,
                competition=comp,
                name="Einzelwertung",
                kind=Scoring.Kind.INDIVIDUAL,
                sort_order=1,
                shots=5,
                counted_shots=3,
                max_per_shot=Decimal(10),
                prize_places=10,
                shootoff_shots=3,
            )
            label = self.org.department_label or "Untereinheit"
            Scoring.objects.create(
                organization=self.org,
                competition=comp,
                name=f"{label}wertung" if " " not in label else f"Wertung {label}",
                kind=Scoring.Kind.UNIT,
                sort_order=2,
                source=single,
                team_mode=Scoring.TeamMode.SUM_BEST,
                team_size=5,
                prize_places=3,
                shootoff_shots=1,
            )
        elif template == "einfach":
            Scoring.objects.create(
                organization=self.org, competition=comp, name="Einzelwertung", sort_order=1
            )
        elif template == "vogel" or comp.form == Competition.Form.BIRD:
            if comp.form != Competition.Form.BIRD:
                comp.form = Competition.Form.BIRD
                comp.save(update_fields=["form"])
            bird.create_template(self.org, comp)
        elif template == "fremd" or not comp.own:
            # Fremder Wettbewerb: eigene Schützen und Mannschaften mit Platz des Ausrichters
            if comp.own:
                comp.own = False
                comp.save(update_fields=["own"])
            Scoring.objects.create(
                organization=self.org,
                competition=comp,
                name="Einzelwertung",
                kind=Scoring.Kind.INDIVIDUAL,
                sort_order=1,
            )
            Scoring.objects.create(
                organization=self.org,
                competition=comp,
                name="Mannschaftswertung",
                kind=Scoring.Kind.TEAM,
                sort_order=2,
            )
            Team.objects.create(organization=self.org, competition=comp, name="Mannschaft 1")

    def _calendar(self, comp: Competition) -> None:
        """Beim Anlegen: Termin zuordnen (``event``) oder neu anlegen (``create_event``)."""
        from . import event_views

        if self.request.data.get("event"):
            event = event_views.find_event(self, self.request.data["event"])
            event_views.link(self, comp, event, fill=True)
        elif self.request.data.get("create_event") is True:
            event_views.create_event(self, comp)

    def retrieve(self, request, *args, **kwargs):
        from access.catalog import EVENTS_MANAGE

        from . import event_views

        comp = self.get_object()
        data = CompetitionSerializer(comp).data
        data["scorings"] = ScoringSerializer(
            comp.scorings.all(), many=True, context={"competition": comp}
        ).data
        data["units"] = [{"id": u.pk, "name": u.name} for u in _units(self.org)]
        data["prizes"] = [
            {"id": p.pk, "name": p.name, "award": p.award, "sort_order": p.sort_order}
            for p in comp.prizes.all()
        ]
        data["can_manage"] = self.can_manage
        # Standzugang anlegen: auch mit „Ergebnisse erfassen“ (stand_views.StandAccessListView)
        data["can_stand_access"] = bool(
            {COMPETITIONS_MANAGE, COMPETITIONS_RESULTS} & self.org_permissions
        )
        from .program_views import ProgramSerializer

        data["programs"] = ProgramSerializer(comp.programs.all(), many=True).data
        from .award_views import award_data

        data["awards"] = [award_data(a) for a in comp.awards.select_related("dignity", "trophy")]
        data["grants"] = [
            awards.grant_data(g)
            for g in comp.grants.select_related("competition", "trophy", "dignity")
        ]
        data["series_name"] = comp.series.name if comp.series_id else ""
        data["from_call"] = _from_internal_call(comp)
        data["event_info"] = event_views.event_info(comp.event)
        on = event_views.calendar_on(self.org)
        data["calendar"] = {"on": on, "can_create": on and EVENTS_MANAGE in self.org_permissions}
        return Response(data)


class ScoringViewSet(_Mixin, AuditMixin, viewsets.ModelViewSet):
    serializer_class = ScoringSerializer

    def get_queryset(self):
        return Scoring.objects.filter(
            organization=self.org, competition_id=self.kwargs["competition_id"]
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if getattr(self, "org", None) is not None:
            ctx["competition"] = self.competition(self.kwargs["competition_id"])
        return ctx

    def get_create_kwargs(self) -> dict:
        comp = self.competition(self.kwargs["competition_id"])
        last = comp.scorings.aggregate(m=Max("sort_order"))["m"] or 0
        return {"organization": self.org, "competition": comp, "sort_order": last + 1}

    @transaction.atomic
    def perform_create(self, serializer):
        comp = Competition.objects.select_for_update().get(pk=serializer.context["competition"].pk)
        serializer.context["competition"] = comp
        fresh = self._revalidate(serializer)
        super().perform_create(fresh)
        serializer.instance = fresh.instance
        from .target_views import recompute_all

        scoring = serializer.instance
        recompute_all(self.org, self.request.user, scoring.competition, scoring)

    @transaction.atomic
    def perform_update(self, serializer):
        comp = Competition.objects.select_for_update().get(pk=serializer.instance.competition_id)
        serializer.context["competition"] = comp
        super().perform_update(self._revalidate(serializer))

    @transaction.atomic
    def perform_destroy(self, instance):
        comp = Competition.objects.select_for_update().get(pk=instance.competition_id)
        if comp.status == Competition.Status.FINAL:
            raise ValidationError(gettext("Der Wettbewerb ist endgültig abgeschlossen."))
        super().perform_destroy(instance)

    def _update(self, serializer):
        from . import target_views

        inst = serializer.instance
        conditions = {
            key: serializer.validated_data[key]
            for key in ("target", "custom_target", "shots")
            if key in serializer.validated_data
            and serializer.validated_data[key] != getattr(inst, key)
        }
        if (
            conditions
            and inst.program_id
            and serializer.validated_data.get("program", inst.program) == inst.program
        ):
            from .program_views import ProgramSerializer

            program_serializer = ProgramSerializer(
                inst.program,
                data={
                    **conditions,
                    "confirm_recalculation": bool(
                        serializer.validated_data.get("confirm_recalculation")
                    ),
                },
                partial=True,
                context={"competition": inst.competition, "request": self.request},
            )
            program_serializer.is_valid(raise_exception=True)
            program_serializer.save()
        keys = ("target", "custom_target", "method", "counted_shots", "program")
        before = {k: getattr(inst, k) for k in keys}
        super()._update(serializer)
        if any(getattr(serializer.instance, k) != before[k] for k in keys):
            sc = serializer.instance
            target_views.recompute_all(self.org, self.request.user, sc.competition, sc)
            Competition.objects.filter(pk=sc.competition_id).update(generation=F("generation") + 1)


class StartersView(_Mixin, APIView):
    """GET: Starter mit Werten · POST: Mitglied (membership) oder Gast (name, club) hinzufügen."""

    manage_only = False

    def get(self, request, org_id: int, competition_id: int):
        return Response(_starters_with_values(self.competition(competition_id)))

    def post(self, request, org_id: int, competition_id: int):
        comp = self.competition(competition_id)
        s = create_starter(self.org, request.user, comp, request.data)
        return Response(_starter_data(s), status=status.HTTP_201_CREATED)


class StarterView(_Mixin, APIView):
    """PATCH: Untereinheit, Startnummer, außer Konkurrenz, Gastname · DELETE: entfernen."""

    manage_only = False

    def _get(self, competition_id, pk) -> Starter:
        comp = self.competition(competition_id)
        if comp.status == Competition.Status.FINAL:
            raise ValidationError(gettext("Der Wettbewerb ist endgültig abgeschlossen."))
        return get_object_or_404(Starter, pk=pk, competition=comp, organization=self.org)

    def patch(self, request, org_id: int, competition_id: int, pk: int):
        s = self._get(competition_id, pk)
        update_starter(self.org, request.user, s, request.data)
        s = Starter.objects.select_related("unit").get(pk=s.pk)
        return Response(_starter_data(s))

    def delete(self, request, org_id: int, competition_id: int, pk: int):
        delete_starter(self.org, request.user, self._get(competition_id, pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


class ScoreView(_Mixin, APIView):
    """PUT {starter, scoring, value}: Wert setzen (leer: löschen)."""

    manage_only = False

    def put(self, request, org_id: int, competition_id: int):
        comp = self.competition(competition_id)
        starter = get_object_or_404(Starter, pk=request.data.get("starter"), competition=comp)
        scoring = get_object_or_404(
            Scoring, pk=request.data.get("scoring"), competition=comp, kind=Scoring.Kind.INDIVIDUAL
        )
        value, _ = set_score(
            self.org, request.user, comp, scoring, starter, request.data.get("value")
        )
        return Response(
            {
                "starter": starter.pk,
                "scoring": scoring.pk,
                "value": None if value is None else str(value),
            }
        )


class SyncView(_Mixin, APIView):
    """POST {ops: [...]}: Eingaben aus dem Offline-Betrieb des Standmodus nachreichen.

    Arten: ``starter`` (wie POST starters, mit ``client_key``), ``starter_update``
    (``starter`` = Nummer oder Gerätekennung, dazu unit/number/out_of_competition) und
    ``score`` (``starter``, ``scoring``, ``value``, ``at``). Jede Eingabe für sich: Was
    scheitert, steht mit Grund in ``results``, der Rest wird übernommen. Zurück kommen
    alle Starter mit Werten und die Zuordnung Gerätekennung → Nummer.
    """

    manage_only = False

    def post(self, request, org_id: int, competition_id: int):
        comp = self.competition(competition_id)
        data = request.data
        return Response(sync(self.org, request.user, comp, data.get("ops"), data.get("generation")))


class MemberListView(_Mixin, APIView):
    """GET: alle Mitglieder am Wettbewerbstag mit Untereinheit, für die Suche ohne Netz
    (nur Name, Zug, Geburtsjahr)."""

    manage_only = False

    def get(self, request, org_id: int, competition_id: int):
        comp = self.competition(competition_id)
        on = comp.date
        rows = (
            Membership.objects.filter(organization=self.org, purged_at__isnull=True)
            .filter(periods__entry_date__lte=on)
            .filter(Q(periods__exit_date__isnull=True) | Q(periods__exit_date__gte=on))
            .distinct()
            .select_related("person")
        )
        units = services.units_on(self.org, on)
        names = dict(Department.objects.filter(organization=self.org).values_list("pk", "name"))
        return Response(
            [
                {
                    "membership": m.pk,
                    "name": _person_name(m),
                    "birth_year": m.person.birth_date.year if m.person.birth_date else None,
                    "unit": units.get(m.pk),
                    "unit_name": names.get(units.get(m.pk), ""),
                }
                for m in sorted(rows, key=lambda m: (m.person.last_name, m.person.first_name))
            ]
        )


class CandidatesView(_Mixin, APIView):
    """GET ?suche=: Mitglieder zur Auswahl als Starter, mit Untereinheit und Geburtsjahr."""

    manage_only = False

    def get(self, request, org_id: int, competition_id: int):
        comp = self.competition(competition_id)
        term = request.query_params.get("suche", "").strip()
        if len(term) < 2:
            return Response([])
        qs = Membership.objects.filter(organization=self.org, purged_at__isnull=True)
        on = comp.date
        # Mitglied am Wettbewerbstag (ein Zeitraum umfasst den Tag)
        qs = (
            qs.filter(periods__entry_date__lte=on)
            .filter(Q(periods__exit_date__isnull=True) | Q(periods__exit_date__gte=on))
            .distinct()
        )
        qs = filter_names(qs, term, variants=_umlaut_variants)
        rows = list(ordered(qs.select_related("person"), limit=12))
        taken = dict(comp.starters.filter(membership__in=rows).values_list("membership_id", "pk"))
        units = dict(Department.objects.filter(organization=self.org).values_list("pk", "name"))
        out = []
        for m in rows:
            unit_id = services.default_unit(self.org, m, on)
            out.append(
                {
                    "membership": m.pk,
                    "name": _person_name(m),
                    "birth_year": m.person.birth_date.year if m.person.birth_date else None,
                    "unit": unit_id,
                    "unit_name": units.get(unit_id, ""),
                    "starter": taken.get(m.pk),
                }
            )
        return Response(out)


class StandingsView(_Mixin, APIView):
    def get(self, request, org_id: int, competition_id: int):
        comp = self.competition(competition_id)
        data = services.standings(comp)
        data["status"] = comp.status
        return Response(_jsonable(data))


class VersionView(_Mixin, APIView):
    """GET: kleiner Stand des Wettbewerbs; die Ansichten laden nur bei einer Änderung neu."""

    def get(self, request, org_id: int, competition_id: int):
        return Response({"version": services.version(self.competition(competition_id))})


class StatusView(_Mixin, APIView):
    """POST {status}: Zustand setzen. „endgültig“ nur ohne offene Stechen."""

    @transaction.atomic
    def post(self, request, org_id: int, competition_id: int):
        comp = Competition.objects.select_for_update().get(pk=self.competition(competition_id).pk)
        new = request.data.get("status")
        if new not in Competition.Status.values:
            raise ValidationError({"status": gettext("Unbekannter Zustand.")})
        if new == Competition.Status.FINAL:
            data = services.standings(comp)
            if data["open_shootoffs"]:
                raise ValidationError(
                    {
                        "status": gettext(
                            "Erst die offenen Stechen entscheiden, dann endgültig setzen."
                        )
                    }
                )
        before = snapshot(comp)
        was_final = comp.status == Competition.Status.FINAL
        comp.status = new
        comp.save(update_fields=["status", "updated_at"])
        record(self.org, request.user, "update", comp, diff(before, snapshot(comp)))
        # Auszeichnungen (Schritt 4): beim Abschluss vergeben, bei einer Korrektur zurück
        if new == Competition.Status.FINAL:
            awards.grant(comp)
        elif was_final:
            awards.withdraw(comp)
        return Response({"status": comp.status, "status_label": comp.get_status_display()})


class ResetView(_Mixin, APIView):
    """POST {keep_starters}: Ergebnisse löschen (Werte, Stechen, Plätze, Schüsse, gefallene
    Pfänder), ohne ``keep_starters`` auch alle Starter (Ralf 2026-11-01). Regeln, Pfänder,
    Mannschaften, Standzugang und Termin bleiben; der Zustand geht auf „Vorbereitung“."""

    @transaction.atomic
    def post(self, request, org_id: int, competition_id: int):
        comp = self.competition(competition_id)
        Competition.objects.select_for_update().filter(pk=comp.pk).first()
        if comp.status == Competition.Status.FINAL:
            raise ValidationError(
                gettext("Ein endgültiger Wettbewerb lässt sich nicht zurücksetzen.")
            )
        keep = bool(request.data.get("keep_starters"))
        before = snapshot(comp)
        counts = {
            "Werte": Score.objects.filter(scoring__competition=comp).count(),
            "Schüsse": comp.shots.count(),
            "Starter": 0 if keep else comp.starters.count(),
        }
        Score.objects.filter(scoring__competition=comp).delete()
        Hit.objects.filter(Q(program__competition=comp) | Q(scoring__competition=comp)).delete()
        ShootOff.objects.filter(scoring__competition=comp).delete()
        Placing.objects.filter(scoring__competition=comp).delete()
        comp.prizes.update(
            winner=None,
            winner_name="",
            shot_number=None,
            shots_for=None,
            shot=None,
            fallen_at=None,
        )
        comp.shots.all().delete()
        if keep:
            comp.starters.exclude(presence="").update(presence="")
        else:
            comp.starters.all().delete()
        comp.status = Competition.Status.PREPARATION
        comp.total_shots = None
        comp.generation += 1
        comp.save(update_fields=["status", "total_shots", "generation", "updated_at"])
        changes = diff(before, snapshot(comp))
        changes["zurückgesetzt"] = [
            ", ".join(f"{n} {k}" for k, n in counts.items() if n) or "nichts",
            "Starter behalten" if keep else "Starter gelöscht",
        ]
        record(self.org, request.user, "update", comp, changes)
        return Response({"deleted": counts, "status": comp.status, "generation": comp.generation})


class CopyView(_Mixin, APIView):
    """POST {date?, title?}: Wettbewerb mit Wertungen kopieren (z. B. aus dem Vorjahr)."""

    @transaction.atomic
    def post(self, request, org_id: int, competition_id: int):
        src = self.competition(competition_id)
        try:
            date = datetime.date.fromisoformat(str(request.data.get("date") or ""))
        except ValueError:
            date = (
                src.date.replace(year=src.date.year + 1)
                if not (src.date.month == 2 and src.date.day == 29)
                else src.date.replace(year=src.date.year + 1, day=28)
            )
        title = str(request.data.get("title") or "").strip()[:200]
        if not title:
            title = src.title.replace(str(src.date.year), str(date.year))
        comp = Competition.objects.create(
            organization=self.org,
            title=title,
            form=src.form,
            own=src.own,
            organizer=src.organizer,
            drop_out=src.drop_out,
            fixed_order=src.fixed_order,
            lots=src.lots,
            occasion=src.occasion,
            discipline=src.discipline,
            location=src.location,
            date=date,
            description=src.description,
            details=src.details,
            website=src.website,
            website_depth=src.website_depth,
            share_ranking=src.share_ranking,
            certificate_template=src.certificate_template,
            series=src.series,
        )
        program_mapping = {}
        for program in src.programs.all():
            old_id = program.pk
            program.pk = None
            program._state.adding = True
            program.competition = comp
            program.save()
            program_mapping[old_id] = program.pk
        mapping = {}
        for sc in src.scorings.order_by("sort_order", "pk"):
            old_pk, source_id = sc.pk, sc.source_id
            sc.pk = None
            sc.id = None
            sc._state.adding = True
            sc.competition = comp
            sc.program_id = program_mapping.get(sc.program_id)
            sc.source_id = mapping.get(source_id)
            sc.save()
            mapping[old_pk] = sc.pk
        for p in src.prizes.all():
            Prize.objects.create(
                organization=self.org,
                competition=comp,
                name=p.name,
                sort_order=p.sort_order,
                award=p.award,
            )
        for t in src.teams.all():
            Team.objects.create(
                organization=self.org, competition=comp, name=t.name, sort_order=t.sort_order
            )
        prize_map = {
            old.pk: new.pk for old, new in zip(src.prizes.all(), comp.prizes.all(), strict=False)
        }
        for a in src.awards.all():
            Award.objects.create(
                organization=self.org,
                competition=comp,
                scoring_id=mapping.get(a.scoring_id),
                prize_id=prize_map.get(a.prize_id),
                place_from=a.place_from,
                place_to=a.place_to,
                title=a.title,
                item=a.item,
                dignity_id=a.dignity_id,
                trophy_id=a.trophy_id,
                sort_order=a.sort_order,
            )
        record(self.org, request.user, "create", comp, diff({}, snapshot(comp)))
        return Response({"id": comp.pk}, status=status.HTTP_201_CREATED)


class ShootOffsView(_Mixin, APIView):
    """GET: alle Stechen · POST {scoring, keys, shots?, counted_shots?}: Stechen für eine
    Gleichstandsgruppe anlegen."""

    manage_only = False

    def get(self, request, org_id: int, competition_id: int):
        return Response(list_shootoffs(self.competition(competition_id)))

    def post(self, request, org_id: int, competition_id: int):
        comp = self.competition(competition_id)
        data = create_shootoff(self.org, request.user, comp, request.data)
        return Response(data, status=status.HTTP_201_CREATED)


class ShootOffView(_Mixin, APIView):
    """PATCH {shots?, counted_shots?}: Regeln ändern, solange kein Wert eingetragen ist ·
    DELETE: Stechen entfernen (nur das letzte einer Wertung)."""

    manage_only = False

    def patch(self, request, org_id: int, competition_id: int, pk: int):
        comp = self.competition(competition_id)
        return Response(update_shootoff(self.org, request.user, comp, pk, request.data))

    def delete(self, request, org_id: int, competition_id: int, pk: int):
        delete_shootoff(self.org, request.user, self.competition(competition_id), pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ShootOffEntryView(_Mixin, APIView):
    """PATCH {value?, membership?, name?}: Wert im Stechen, bei Untereinheiten den Schützen."""

    manage_only = False

    def patch(self, request, org_id: int, competition_id: int, pk: int):
        comp = self.competition(competition_id)
        return Response(update_shootoff_entry(self.org, request.user, comp, pk, request.data))


class UnitMembersView(_Mixin, APIView):
    """GET ?unit=: Mitglieder einer Untereinheit am Wettbewerbstag (Schütze im Stechen)."""

    manage_only = False

    def get(self, request, org_id: int, competition_id: int):
        comp = self.competition(competition_id)
        return Response(unit_members(self.org, comp, request.query_params.get("unit")))


class ExportView(_Mixin, APIView):
    """GET ?als=pdf|xlsx: Auswertung als PDF oder Excel."""

    def get(self, request, org_id: int, competition_id: int):
        comp = self.competition(competition_id)
        kind = request.query_params.get("als", "pdf")
        name = report.filename(comp)
        if kind == "schiessliste":
            try:
                blank = max(0, min(int(request.query_params.get("leerzeilen", 10)), 60))
            except ValueError:
                blank = 10
            body = report.shooting_list(
                comp,
                order=request.query_params.get("sortierung", "name"),
                blank_rows=blank,
                empty=request.query_params.get("leer") == "1",
            )
            resp = HttpResponse(body, content_type="application/pdf")
            resp["Content-Disposition"] = (
                f'inline; filename="{name.replace("Auswertung", "Schiessliste")}.pdf"'
            )
            return resp
        if kind in ("losliste", "pfaenderliste"):
            if comp.form != Competition.Form.BIRD:
                raise ValidationError(gettext("Das ist kein Vogelschießen."))
            if kind == "losliste":
                try:
                    blank = max(0, min(int(request.query_params.get("leerzeilen", 10)), 60))
                except ValueError:
                    blank = 10
                body, label = report.lot_list(comp, blank), "Losliste"
            else:
                body, label = report.prize_sheet(comp), "Pfaenderliste"
            resp = HttpResponse(body, content_type="application/pdf")
            resp["Content-Disposition"] = (
                f'inline; filename="{name.replace("Auswertung", label)}.pdf"'
            )
            return resp
        if kind == "stechliste":
            so = get_object_or_404(
                ShootOff, pk=request.query_params.get("stechen") or 0, scoring__competition=comp
            )
            resp = HttpResponse(report.shootoff_list(comp, so), content_type="application/pdf")
            resp["Content-Disposition"] = f'inline; filename="Stechliste-{so.number}.pdf"'
            return resp
        if kind == "xlsx":
            body = report.xlsx(comp)
            resp = HttpResponse(
                body,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            resp["Content-Disposition"] = f'attachment; filename="{name}.xlsx"'
            return resp
        resp = HttpResponse(report.pdf(comp), content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="{name}.pdf"'
        return resp


class GuestsAdultView(_Mixin, APIView):
    """Gäste und frei eingetragene Gewinner: „volljährig“ angeben oder nachtragen.

    GET: Liste · POST ``{"starters": {id: bool}, "prizes": {id: bool}}`` oder ``{"all": true}``
    (alle Gäste und freien Gewinner dieses Wettbewerbs volljährig). Auch bei abgeschlossenen
    Wettbewerben: Es ändert nur, ob der Name auf der Webseite erscheint (FF-24 (c), PF-21)."""

    def _rows(self, comp):
        starters = [
            {"kind": "starter", "id": s.pk, "name": s.name, "club": s.club, "adult": s.guest_adult}
            for s in Starter.objects.filter(
                competition=comp, organization=self.org, membership__isnull=True
            ).order_by("pk")
        ]
        prizes = [
            {
                "kind": "prize",
                "id": p.pk,
                "name": p.winner_name,
                "club": p.name,
                "adult": p.winner_adult,
            }
            for p in Prize.objects.filter(competition=comp, winner__isnull=True).order_by("pk")
            if p.winner_name
        ]
        return starters + prizes

    def get(self, request, org_id: int, competition_id: int):
        return Response(self._rows(self.competition(competition_id)))

    @transaction.atomic
    def post(self, request, org_id: int, competition_id: int):
        comp = self.competition(competition_id)
        data = request.data or {}
        if data.get("all"):
            wanted_starters = {
                s.pk: True
                for s in Starter.objects.filter(
                    competition=comp, organization=self.org, membership__isnull=True
                )
            }
            wanted_prizes = {
                p.pk: True
                for p in Prize.objects.filter(competition=comp, winner__isnull=True)
                if p.winner_name
            }
        else:
            try:
                wanted_starters = {int(k): bool(v) for k, v in (data.get("starters") or {}).items()}
                wanted_prizes = {int(k): bool(v) for k, v in (data.get("prizes") or {}).items()}
            except (TypeError, ValueError, AttributeError) as exc:
                raise ValidationError(gettext("Ungültige Angabe.")) from exc
        for s in Starter.objects.filter(
            competition=comp,
            organization=self.org,
            membership__isnull=True,
            pk__in=wanted_starters,
        ):
            if s.guest_adult != wanted_starters[s.pk]:
                before = snapshot(s)
                s.guest_adult = wanted_starters[s.pk]
                s.save(update_fields=["guest_adult", "updated_at"])
                record(self.org, request.user, "update", s, diff(before, snapshot(s)))
        for p in Prize.objects.filter(competition=comp, winner__isnull=True, pk__in=wanted_prizes):
            if p.winner_adult != wanted_prizes[p.pk]:
                before = snapshot(p)
                p.winner_adult = wanted_prizes[p.pk]
                p.save(update_fields=["winner_adult"])
                record(self.org, request.user, "update", p, diff(before, snapshot(p)))
        return Response(self._rows(comp))
