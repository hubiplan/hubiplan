"""Verwaltung der Umfragen (Verein und Untereinheit): anlegen, starten, Ergebnis, Export."""

from __future__ import annotations

import datetime

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import diff, record, snapshot

from . import access, exports, services
from .models import (
    MAX_OPTIONS,
    MAX_QUESTIONS,
    Survey,
    SurveyAnswer,
    SurveyOption,
    SurveyParticipation,
    SurveyQuestion,
)

Kind = SurveyQuestion.Kind
MAX_DURATION = datetime.timedelta(days=366)
OPTION_KINDS = (Kind.SINGLE, Kind.MULTIPLE, Kind.QUANTITY, Kind.DATES)


def conflict():
    exc = APIException(_("Die Umfrage wurde inzwischen geändert. Bitte neu laden."))
    exc.status_code = 409
    return exc


class Base(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.scope = access.scope_for(request.user, kwargs.get("org_id"), kwargs.get("dept_id"))

    def surveys(self):
        return Survey.objects.filter(
            organization=self.scope.org, department_id=self.scope.department_id
        )

    def survey(self, pk, *, lock=False):
        qs = self.surveys().select_related("event", "follow_event", "department", "organization")
        if lock:
            qs = qs.select_for_update(of=("self",))
        return get_object_or_404(qs, pk=pk)

    def event(self, pk):
        from events.models import Event

        if not pk:
            return None
        event = Event.objects.filter(
            organization=self.scope.org, department_id=self.scope.department_id, pk=pk
        ).first()
        if event is None:
            raise ValidationError({"event": _("Unbekannter Termin.")})
        return event

    def department(self):
        from organizations.models import Department

        if self.scope.department_id is None:
            return None
        return Department.objects.get(pk=self.scope.department_id)


def can_create_event(scope) -> bool:
    codes = {"dept.events.manage"} if scope.department_id else {"events.manage", "events.edit"}
    return scope.can_edit and bool(codes & scope.permissions)


def question_data(q: SurveyQuestion) -> dict:
    return {
        "id": q.pk,
        "kind": q.kind,
        "text": q.text,
        "required": q.required,
        "max_choices": q.max_choices,
        "allow_maybe": q.allow_maybe,
        "options": [
            {
                "id": o.pk,
                "label": o.label,
                "starts_at": o.starts_at,
                "ends_at": o.ends_at,
                "all_day": o.all_day,
                "capacity": o.capacity,
            }
            for o in q.options.all()
        ],
    }


def survey_data(survey: Survey, scope, *, full=False, count=None) -> dict:
    status = services.status_of(survey)
    if count is None:
        count = services.participants(survey)
    data = {
        "id": survey.pk,
        "title": survey.title,
        "description": survey.description,
        "event": survey.event_id,
        "event_title": survey.event.title if survey.event_id else "",
        "event_starts_at": survey.event.starts_at if survey.event_id else None,
        "audience": survey.audience,
        "filters": survey.filters or {},
        "persons": survey.persons or [],
        "names": survey.names,
        "results": survey.results,
        "status": status,
        "closes_at": survey.closes_at,
        "remind_days": survey.remind_days,
        "keep_months": survey.keep_months,
        "opened_at": survey.opened_at,
        "closed_at": survey.closed_at,
        "purged_at": survey.purged_at,
        "participants": count,
        "invited": survey.invited,
        "follow_event": survey.follow_event_id,
        "version": survey.version,
        "can_edit": scope.can_edit,
        "can_create_event": can_create_event(scope),
    }
    if full:
        data["questions"] = [question_data(q) for q in survey.questions.prefetch_related("options")]
        if status != Survey.Status.DRAFT and survey.purged_at is None:
            ids = services.eligible_ids(survey) if status == Survey.Status.OPEN else None
            if ids is not None:
                data["invited"] = len(ids)
            if not survey.anonymous:
                done = set(
                    SurveyParticipation.objects.filter(survey=survey).values_list(
                        "membership_id", flat=True
                    )
                )
                if ids is not None:
                    from members.models import Membership
                    from members.personsearch import ordered

                    pending = ordered(
                        Membership.objects.filter(pk__in=[i for i in ids if i not in done])
                    )
                    data["pending"] = [services.person_name(m) for m in pending[:500]]
        data["result"] = (
            services.result_data(survey, with_names=True) if status != Survey.Status.DRAFT else None
        )
        data["persons_named"] = _persons_named(survey)
    return data


def _persons_named(survey: Survey) -> list[dict]:
    from members.models import Membership

    ids = services.as_ints(survey.persons)
    if not ids:
        return []
    rows = Membership.objects.filter(organization=survey.organization, pk__in=ids).select_related(
        "person"
    )
    return [{"id": m.pk, "name": services.person_name(m)} for m in rows]


class OptionInput(serializers.Serializer):
    label = serializers.CharField(max_length=200, allow_blank=True, required=False, default="")
    starts_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    ends_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    all_day = serializers.BooleanField(required=False, default=False)
    capacity = serializers.IntegerField(
        min_value=1, max_value=100000, required=False, allow_null=True, default=None
    )


class QuestionInput(serializers.Serializer):
    kind = serializers.ChoiceField(choices=Kind.choices)
    text = serializers.CharField(max_length=1000)
    required = serializers.BooleanField(required=False, default=True)
    max_choices = serializers.IntegerField(
        min_value=1, max_value=50, required=False, allow_null=True, default=None
    )
    allow_maybe = serializers.BooleanField(required=False, default=True)
    options = OptionInput(many=True, required=False, default=list)


class SurveyInput(serializers.Serializer):
    version = serializers.IntegerField(required=False)
    title = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(max_length=5000, allow_blank=True, required=False)
    event = serializers.IntegerField(min_value=1, allow_null=True, required=False)
    audience = serializers.ChoiceField(choices=Survey.Audience.choices, required=False)
    filters = serializers.DictField(required=False)
    persons = serializers.ListField(
        child=serializers.IntegerField(min_value=1), max_length=2000, required=False
    )
    names = serializers.ChoiceField(choices=Survey.Names.choices, required=False)
    results = serializers.ChoiceField(choices=Survey.Results.choices, required=False)
    closes_at = serializers.DateTimeField(required=False, allow_null=True)
    remind_days = serializers.IntegerField(
        min_value=1, max_value=14, allow_null=True, required=False
    )
    keep_months = serializers.IntegerField(min_value=1, max_value=60, required=False)
    questions = QuestionInput(many=True, required=False)


FILTER_KEYS = ("departments", "member_types", "roles", "board", "age_min", "age_max", "selected")


def clean_filters(raw: dict) -> dict:
    out = {}
    for key in FILTER_KEYS:
        if key not in raw:
            continue
        value = raw[key]
        if key == "board":
            out[key] = bool(value)
        elif key in ("age_min", "age_max"):
            if value is None or value == "":
                continue
            if not isinstance(value, int) or not 0 <= value <= 120:
                raise ValidationError({"filters": _("Ungültiges Alter.")})
            out[key] = value
        elif key == "selected":
            out[key] = [v for v in value if isinstance(v, str)] if isinstance(value, list) else []
        else:
            out[key] = services.as_ints(value)
    return out


def check_questions(rows: list[dict]) -> None:
    if len(rows) > MAX_QUESTIONS:
        raise ValidationError(
            {"questions": _("Höchstens {n} Fragen je Umfrage.").format(n=MAX_QUESTIONS)}
        )
    for q in rows:
        if not q["text"].strip():
            raise ValidationError({"questions": _("Bitte jede Frage ausfüllen.")})
        options = q.get("options") or []
        if q["kind"] not in OPTION_KINDS:
            if options:
                raise ValidationError(
                    {"questions": _("Diese Frageart hat keine Antwortmöglichkeiten.")}
                )
            continue
        if len(options) > MAX_OPTIONS:
            raise ValidationError(
                {"questions": _("Höchstens {n} Antworten je Frage.").format(n=MAX_OPTIONS)}
            )
        least = 1 if q["kind"] == Kind.QUANTITY else 2
        if len(options) < least:
            raise ValidationError(
                {
                    "questions": _("„{text}“ braucht mindestens {n} Antworten.").format(
                        text=q["text"].strip(), n=least
                    )
                }
            )
        for o in options:
            if q["kind"] == Kind.DATES:
                if not o.get("starts_at"):
                    raise ValidationError(
                        {"questions": _("Bitte für jeden Terminvorschlag den Beginn angeben.")}
                    )
                if o.get("ends_at") and o["ends_at"] < o["starts_at"]:
                    raise ValidationError(
                        {"questions": _("Ein Terminvorschlag endet vor seinem Beginn.")}
                    )
            elif not (o.get("label") or "").strip():
                raise ValidationError({"questions": _("Bitte jede Antwort ausfüllen.")})


def save_questions(survey: Survey, rows: list[dict]) -> None:
    survey.questions.all().delete()
    for i, q in enumerate(rows):
        kind = q["kind"]
        question = SurveyQuestion.objects.create(
            organization_id=survey.organization_id,
            survey=survey,
            position=i,
            kind=kind,
            text=q["text"].strip(),
            required=q.get("required", True),
            max_choices=q.get("max_choices") if kind in (Kind.MULTIPLE, Kind.QUANTITY) else None,
            allow_maybe=q.get("allow_maybe", True),
        )
        if kind not in OPTION_KINDS:
            continue
        for j, o in enumerate(q.get("options") or []):
            SurveyOption.objects.create(
                organization_id=survey.organization_id,
                question=question,
                position=j,
                label=(o.get("label") or "").strip(),
                starts_at=o.get("starts_at") if kind == Kind.DATES else None,
                ends_at=o.get("ends_at") if kind == Kind.DATES else None,
                all_day=bool(o.get("all_day")) if kind == Kind.DATES else False,
                capacity=o.get("capacity") if kind != Kind.DATES else o.get("capacity"),
            )


def check_persons(view, ids: list[int]) -> list[int]:
    from circulars.recipients import club_base

    base = club_base(view.scope.org, view.department())
    found = set(base.filter(pk__in=ids).values_list("pk", flat=True))
    if set(ids) - found:
        raise ValidationError({"persons": _("Unbekannte Person.")})
    return sorted(found)


def apply(view, survey: Survey, data: dict, *, creating: bool) -> None:
    status = services.status_of(survey) if not creating else Survey.Status.DRAFT
    draft = status == Survey.Status.DRAFT
    started = not draft
    if "title" in data:
        title = data["title"].strip()
        if not title:
            raise ValidationError({"title": _("Bitte einen Titel angeben.")})
        survey.title = title
    if "description" in data:
        survey.description = data["description"].strip()
    for field in ("event", "audience", "filters", "persons", "questions"):
        if field in data and started:
            raise ValidationError(
                {"detail": _("Fragen und Zielgruppe lassen sich nach dem Start nicht mehr ändern.")}
            )
    if "event" in data:
        survey.event = view.event(data["event"])
    if "audience" in data:
        survey.audience = data["audience"]
    if "filters" in data:
        survey.filters = clean_filters(data["filters"])
    if "persons" in data:
        survey.persons = check_persons(view, data["persons"])
    if "names" in data and data["names"] != survey.names:
        if (
            started
            and services.participants(survey)
            and not services.stricter(survey.names, data["names"], services.NAMES_ORDER)
        ):
            raise ValidationError(
                {
                    "names": _(
                        "Nach der ersten Antwort lassen sich Namen nur noch strenger schützen."
                    )
                }
            )
        survey.names = data["names"]
        if survey.anonymous and started and survey.pk:
            # Auf anonym umgestellt: Schon gegebene Antworten verlieren die Verbindung zur
            # Person und werden neu gemischt, sonst bliebe die Zuordnung in der Datenbank
            Survey.objects.select_for_update().filter(pk=survey.pk).first()
            SurveyAnswer.objects.filter(survey=survey).update(participation=None)
            services.mix_answers(survey)
    if "results" in data and data["results"] != survey.results:
        # Gesamtaudit 15.11., UM-1: Wer unter „nur die Verwaltung sieht das Ergebnis“
        # geantwortet hat, darf nicht nachträglich für alle sichtbar werden
        if started and not services.stricter(
            survey.results, data["results"], services.RESULTS_ORDER
        ):
            raise ValidationError(
                {"results": _("Nach dem Start lässt sich das Ergebnis nur noch strenger schützen.")}
            )
        survey.results = data["results"]
    if survey.anonymous and survey.results not in services.ANONYMOUS_RESULTS:
        if "results" in data:
            raise ValidationError(
                {"results": _("Anonyme Umfragen zeigen ihr Ergebnis erst nach dem Ende.")}
            )
        # Auf anonym umgestellt: Ergebnis gleich mit verschärfen
        survey.results = Survey.Results.AFTER_CLOSE
    if "closes_at" in data:
        end = data["closes_at"]
        if started and end is None:
            raise ValidationError({"closes_at": _("Bitte ein Ende angeben.")})
        if end is not None and end > timezone.now() + MAX_DURATION:
            raise ValidationError({"closes_at": _("Eine Umfrage läuft höchstens ein Jahr.")})
        if started and status == Survey.Status.OPEN and end <= timezone.now():
            raise ValidationError({"closes_at": _("Das Ende liegt in der Vergangenheit.")})
        survey.closes_at = end
    for field in ("remind_days", "keep_months"):
        if field in data:
            setattr(survey, field, data[field])
    if (
        survey.audience in (Survey.Audience.EVENT, Survey.Audience.EVENT_YES)
        and not survey.event_id
    ):
        raise ValidationError({"audience": _("Bitte einen Termin wählen.")})


class ListView(Base):
    def get(self, request, **kwargs):
        rows = list(self.surveys().select_related("event"))
        counts = services.counts_by_survey(rows)
        return Response([survey_data(s, self.scope, count=counts.get(s.pk, 0)) for s in rows])

    @transaction.atomic
    def post(self, request, **kwargs):
        access.require_edit(self.scope)
        if self.scope.org.type != "club":
            raise NotFound()
        ser = SurveyInput(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        if not (data.get("title") or "").strip():
            raise ValidationError({"title": _("Bitte einen Titel angeben.")})
        survey = Survey(
            organization=self.scope.org,
            department_id=self.scope.department_id,
            created_by=request.user,
        )
        apply(self, survey, data, creating=True)
        survey.save()
        if "questions" in data:
            check_questions(data["questions"])
            save_questions(survey, data["questions"])
        record(self.scope.org, request.user, "create", survey, diff({}, snapshot(survey)))
        return Response(survey_data(survey, self.scope, full=True), status=201)


class DetailView(Base):
    def get(self, request, pk, **kwargs):
        return Response(survey_data(self.survey(pk), self.scope, full=True))

    @transaction.atomic
    def patch(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        survey = self.survey(pk, lock=True)
        if survey.purged_at:
            raise ValidationError({"detail": _("Die Antworten dieser Umfrage sind gelöscht.")})
        before = snapshot(survey)
        ser = SurveyInput(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        if "version" in data and data["version"] != survey.version:
            raise conflict()
        apply(self, survey, data, creating=False)
        if "questions" in data:
            check_questions(data["questions"])
            save_questions(survey, data["questions"])
        survey.version += 1
        survey.save()
        changes = diff(before, snapshot(survey))
        if changes:
            record(self.scope.org, request.user, "update", survey, changes)
        return Response(survey_data(survey, self.scope, full=True))

    @transaction.atomic
    def delete(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        survey = self.survey(pk, lock=True)
        if services.status_of(survey) == Survey.Status.OPEN:
            raise ValidationError({"detail": _("Eine laufende Umfrage bitte zuerst beenden.")})
        record(self.scope.org, request.user, "delete", survey, diff(snapshot(survey), {}))
        survey.delete()
        return Response(status=204)


class StartView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        survey = self.survey(pk, lock=True)
        if survey.status != Survey.Status.DRAFT:
            raise ValidationError({"detail": _("Die Umfrage läuft schon.")})
        now = timezone.now()
        if not survey.questions.exists():
            raise ValidationError({"detail": _("Bitte mindestens eine Frage anlegen.")})
        if survey.closes_at is None or survey.closes_at <= now:
            raise ValidationError({"closes_at": _("Bitte ein Ende in der Zukunft angeben.")})
        if survey.closes_at > now + MAX_DURATION:
            raise ValidationError({"closes_at": _("Eine Umfrage läuft höchstens ein Jahr.")})
        if not services.eligible(survey).exists():
            raise ValidationError({"detail": _("Die Zielgruppe ist leer.")})
        survey.status = Survey.Status.OPEN
        survey.opened_at = now
        survey.version += 1
        survey.save(update_fields=["status", "opened_at", "version", "updated_at"])
        record(self.scope.org, request.user, "update", survey, {"Status": ["Entwurf", "läuft"]})
        from .tasks import notify_start

        transaction.on_commit(lambda: notify_start.delay(survey.pk))
        return Response(survey_data(survey, self.scope, full=True))


class CloseView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        survey = self.survey(pk, lock=True)
        if survey.status != Survey.Status.OPEN:
            raise ValidationError({"detail": _("Die Umfrage läuft nicht.")})
        services.close(survey)
        record(self.scope.org, request.user, "update", survey, {"Status": ["läuft", "beendet"]})
        return Response(survey_data(survey, self.scope, full=True))


class CopyView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        old = self.survey(pk)
        survey = Survey.objects.create(
            organization=old.organization,
            department=old.department,
            event=None if old.event_id and old.event.ends_at < timezone.now() else old.event,
            title=_("{title} (Kopie)").format(title=old.title)[:200],
            description=old.description,
            audience=old.audience
            if old.audience in (Survey.Audience.MEMBERS, Survey.Audience.PERSONS)
            or (old.event_id and old.event.ends_at >= timezone.now())
            else Survey.Audience.MEMBERS,
            filters=old.filters,
            persons=old.persons,
            names=old.names,
            results=old.results,
            remind_days=old.remind_days,
            keep_months=old.keep_months,
            created_by=request.user,
        )
        rows = [question_data(q) for q in old.questions.prefetch_related("options")]
        save_questions(survey, rows)
        record(self.scope.org, request.user, "create", survey, diff({}, snapshot(survey)))
        return Response(survey_data(survey, self.scope, full=True), status=201)


class BoardAnswerInput(serializers.Serializer):
    membership = serializers.IntegerField(min_value=1)
    answers = serializers.ListField(child=serializers.DictField(), max_length=MAX_QUESTIONS)


class AnswersView(Base):
    """Die Verwaltung trägt für ein Mitglied ohne Zugang ein (nur Umfragen mit Namen)."""

    @transaction.atomic
    def post(self, request, pk, **kwargs):
        from members.models import Membership

        access.require_edit(self.scope)
        survey = self.survey(pk, lock=True)
        if survey.anonymous:
            raise ValidationError(
                {"detail": _("Bei anonymen Umfragen trägt die Verwaltung nichts ein.")}
            )
        ser = BoardAnswerInput(data=request.data)
        ser.is_valid(raise_exception=True)
        membership = get_object_or_404(
            Membership.objects.select_related("person"),
            organization=self.scope.org,
            pk=ser.validated_data["membership"],
        )
        services.save_answers(
            survey,
            membership,
            ser.validated_data["answers"],
            source=SurveyParticipation.Source.BOARD,
        )
        record(
            self.scope.org,
            request.user,
            "update",
            survey,
            {f"Antwort eingetragen für {services.person_name(membership)}": [None, "ja"]},
        )
        return Response(survey_data(survey, self.scope, full=True))


class EventFromDateInput(serializers.Serializer):
    option = serializers.IntegerField(min_value=1)


class EventFromDateView(Base):
    """Terminfindung: aus dem gewählten Vorschlag einen Termin mit Zu- und Absagen anlegen."""

    @transaction.atomic
    def post(self, request, pk, **kwargs):
        from events.models import Event

        access.require_edit(self.scope)
        if not can_create_event(self.scope):
            raise PermissionDenied()
        survey = self.survey(pk, lock=True)
        if survey.follow_event_id:
            raise ValidationError({"detail": _("Aus dieser Umfrage gibt es schon einen Termin.")})
        ser = EventFromDateInput(data=request.data)
        ser.is_valid(raise_exception=True)
        option = get_object_or_404(
            SurveyOption.objects.filter(question__survey=survey, question__kind=Kind.DATES),
            pk=ser.validated_data["option"],
        )
        start = option.starts_at
        if option.all_day:
            day = timezone.localtime(start).replace(hour=0, minute=0, second=0, microsecond=0)
            start, end = day, option.ends_at or day
        else:
            end = option.ends_at or start + datetime.timedelta(hours=2)
        event = Event.objects.create(
            organization=self.scope.org,
            department_id=self.scope.department_id,
            title=survey.title[:200],
            description=survey.description[:5000],
            starts_at=start,
            ends_at=end,
            all_day=option.all_day,
            rsvp_enabled=True,
        )
        survey.follow_event = event
        survey.version += 1
        survey.save(update_fields=["follow_event", "version", "updated_at"])
        record(self.scope.org, request.user, "create", event, diff({}, snapshot(event)))
        return Response(survey_data(survey, self.scope, full=True), status=201)


class OptionsView(Base):
    """Auswahl für Zielgruppe und Termin beim Anlegen."""

    def get(self, request, **kwargs):
        from events.models import Event
        from members.models import MemberType
        from organizations.models import Department
        from organizations.tree import with_descendants

        access.require_edit(self.scope)
        org = self.scope.org
        if self.scope.department_id:
            ids = with_descendants(org.pk, [self.scope.department_id]) or [self.scope.department_id]
            units = Department.objects.filter(pk__in=list(ids), is_active=True).exclude(
                pk=self.scope.department_id
            )
        else:
            units = Department.objects.filter(organization=org, is_active=True)
        since = timezone.now() - datetime.timedelta(days=1)
        events = Event.objects.filter(
            organization=org, department_id=self.scope.department_id, ends_at__gte=since
        ).order_by("starts_at")[:200]
        return Response(
            {
                "units": [{"id": d.pk, "name": d.name} for d in units.order_by("name")],
                "member_types": [
                    {"id": t.pk, "name": t.name}
                    for t in MemberType.objects.filter(organization=org).order_by("name")
                ],
                "events": [
                    {
                        "id": e.pk,
                        "title": e.title,
                        "starts_at": e.starts_at,
                        "rsvp_enabled": e.rsvp_enabled,
                        "rsvp_deadline": e.rsvp_deadline,
                    }
                    for e in events
                ],
                "board": self.scope.department_id is None,
            }
        )


class MembersView(Base):
    """Personen suchen (Zielgruppe „ausgewählte Personen“, Eintragen für ein Mitglied)."""

    def get(self, request, **kwargs):
        from circulars.recipients import club_base
        from members.personsearch import filter_names, ordered

        access.require_edit(self.scope)
        term = (request.query_params.get("suche") or "").strip()
        if len(term) < 2:
            return Response([])
        qs = filter_names(club_base(self.scope.org, self.department()), term)
        rows = ordered(qs.select_related("person"), limit=10)
        return Response(
            [
                {
                    "id": m.pk,
                    "first_name": m.person.first_name,
                    "last_name": m.person.last_name,
                    "name": services.person_name(m),
                }
                for m in rows
            ]
        )


class CountView(Base):
    """Wie viele Personen die Zielgruppe hätte (Vorschau beim Anlegen)."""

    def post(self, request, **kwargs):
        access.require_edit(self.scope)
        ser = SurveyInput(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        probe = Survey(
            organization=self.scope.org,
            department=self.department(),
        )
        data = ser.validated_data
        probe.audience = data.get("audience", Survey.Audience.MEMBERS)
        probe.filters = clean_filters(data.get("filters") or {})
        probe.persons = services.as_ints(data.get("persons") or [])
        if data.get("event"):
            probe.event = self.event(data["event"])
        return Response({"count": len(services.eligible_ids(probe))})


class ExportView(Base):
    def get(self, request, pk, **kwargs):
        survey = self.survey(pk)
        if survey.status == Survey.Status.DRAFT:
            raise NotFound()
        fmt = request.query_params.get("datei", "pdf")
        if fmt == "xlsx":
            content = exports.xlsx(survey)
            ctype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        else:
            content = exports.pdf(survey)
            ctype = "application/pdf"
            fmt = "pdf"
        response = HttpResponse(content, content_type=ctype)
        response["Content-Disposition"] = f'attachment; filename="umfrage-{survey.pk}.{fmt}"'
        response["Cache-Control"] = "private, no-store"
        return response
