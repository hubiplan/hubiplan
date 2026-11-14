"""Umfragen im Mitgliederbereich und in der App (/api/portal/<Zugang>/surveys/…)."""

from __future__ import annotations

import datetime

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.tenancy import scope_of, set_rls, user_view

from . import services
from .models import Survey, SurveyParticipation

# Beendete Umfragen bleiben so lange in der Liste
SHOW_CLOSED = datetime.timedelta(days=90)


def portal_access(user, access_id):
    from portal.views import _portal_access

    with user_view(user.pk):
        access = _portal_access(user, access_id)
    set_rls(access.organization_id, user.pk, scope_id=scope_of(access.organization_id))
    if "surveys" not in (access.organization.enabled_modules or []):
        raise NotFound()
    if not access.membership.current_period():
        raise NotFound()
    return access


def question_data(q) -> dict:
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


def follow_data(survey: Survey, membership_id: int, mine) -> dict | None:
    """Aus der Terminfindung angelegter Termin: „Zusage übernehmen?“ für die Ja-Sager (UM-9)."""
    event = survey.follow_event
    if event is None or event.is_cancelled:
        return None
    from events.models import EventResponse

    said_yes = False
    if mine:
        for row in mine:
            for value in (row.get("dates") or {}).values():
                if value == "yes":
                    said_yes = True
    response = EventResponse.objects.filter(event=event, membership_id=membership_id).first()
    return {
        "id": event.pk,
        "title": event.title,
        "starts_at": event.starts_at,
        "ends_at": event.ends_at,
        "all_day": event.all_day,
        "rsvp_enabled": event.rsvp_enabled,
        "said_yes": said_yes,
        "response": response.status if response else None,
    }


def survey_data(survey: Survey, membership_id: int, now=None) -> dict:
    now = now or timezone.now()
    status = services.status_of(survey, now)
    answered = SurveyParticipation.objects.filter(
        survey=survey, membership_id=membership_id
    ).exists()
    mine = services.my_answers(survey, membership_id)
    data = {
        "id": survey.pk,
        "title": survey.title,
        "description": survey.description,
        "unit": survey.department.name if survey.department_id else "",
        "event": (
            {
                "id": survey.event_id,
                "title": survey.event.title,
                "starts_at": survey.event.starts_at,
            }
            if survey.event_id
            else None
        ),
        "status": status,
        "closes_at": survey.closes_at,
        "names": survey.names,
        "results_mode": survey.results,
        "anonymous": survey.anonymous,
        "answered": answered,
        "can_answer": status == Survey.Status.OPEN and not (answered and survey.anonymous),
        "can_change": status == Survey.Status.OPEN and answered and not survey.anonymous,
        "mine": mine,
        "questions": [question_data(q) for q in survey.questions.prefetch_related("options")],
        "results": None,
        "follow_event": follow_data(survey, membership_id, mine),
    }
    for q in data["questions"]:
        if q["kind"] == "quantity":
            q["max_total"] = services.quantity_limit(
                next(x for x in survey.questions.all() if x.pk == q["id"]), membership_id
            )
    if services.member_sees_results(survey, answered, now):
        data["results"] = services.result_data(survey, with_names=survey.names == Survey.Names.OPEN)
    return data


def visible(access, now=None):
    """Umfragen, die das Mitglied sehen darf: offen und an es gerichtet, oder schon beantwortet."""
    now = now or timezone.now()
    member = access.membership_id
    rows = []
    qs = (
        Survey.objects.filter(organization=access.organization)
        .exclude(status=Survey.Status.DRAFT)
        .filter(Q(closes_at__isnull=True) | Q(closes_at__gte=now - SHOW_CLOSED))
        .select_related("department", "event", "follow_event", "organization")
        .order_by("closes_at", "pk")
    )
    answered = services.answered_ids(member, [s.pk for s in qs])
    for survey in qs:
        if survey.pk in answered or services.is_eligible(survey, member):
            rows.append(survey)
    return rows


class Base(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.access = portal_access(request.user, kwargs["access_id"])
        self.org = self.access.organization

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response

    def survey(self, pk, *, lock=False):
        ids = {s.pk for s in visible(self.access)}
        if pk not in ids:
            raise NotFound()
        qs = Survey.objects.select_related("organization", "department", "event", "follow_event")
        if lock:
            qs = qs.select_for_update(of=("self",))
        return get_object_or_404(qs, pk=pk, organization=self.org)


class ListView(Base):
    def get(self, request, **kwargs):
        now = timezone.now()
        member = self.access.membership_id
        rows = [survey_data(s, member, now) for s in visible(self.access, now)]
        # Offene zuerst, dann beendete (neueste zuerst)
        open_ = [r for r in rows if r["status"] == Survey.Status.OPEN]
        closed = [r for r in rows if r["status"] != Survey.Status.OPEN]
        closed.sort(key=lambda r: r["closes_at"] or now, reverse=True)
        return Response({"surveys": open_ + closed})


class DetailView(Base):
    def get(self, request, pk, **kwargs):
        return Response(survey_data(self.survey(pk), self.access.membership_id))


class AnswerView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        survey = self.survey(pk, lock=True)
        services.save_answers(
            survey,
            self.access.membership,
            request.data.get("answers"),
            source=SurveyParticipation.Source.MEMBER,
        )
        return Response(survey_data(survey, self.access.membership_id))

    @transaction.atomic
    def delete(self, request, pk, **kwargs):
        survey = self.survey(pk, lock=True)
        services.withdraw(survey, self.access.membership_id)
        return Response(survey_data(survey, self.access.membership_id))


class FollowView(Base):
    """Zusage zum Termin aus der Terminfindung übernehmen (ein Tipp)."""

    @transaction.atomic
    def post(self, request, pk, **kwargs):
        from events import rsvp
        from events.models import EventResponse

        survey = self.survey(pk)
        event = survey.follow_event
        if event is None or not rsvp.is_invited(event, self.access.membership_id):
            raise NotFound()
        allowed, reason = rsvp.member_can_respond(event)
        if not allowed:
            raise ValidationError(
                {
                    "detail": _(reason)
                    if reason
                    else _("Für diesen Termin gibt es keine Rückmeldung.")
                }
            )
        rsvp.save_response(
            event,
            self.access.membership,
            status=EventResponse.Status.YES,
            guests=0,
            note=None,
            source=EventResponse.Source.MEMBER,
            user=request.user,
        )
        return Response(survey_data(survey, self.access.membership_id))
