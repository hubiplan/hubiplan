"""Umfrage per Link aus der Mail beantworten, ohne Anmeldung.

Wie der Rückmeldelink bei Terminen (events/rsvp_link.py): je Mitglied und Umfrage ein
signierter Link. Erst „Absenden“ (POST) speichert; das bloße Öffnen ändert nichts.
"""

from __future__ import annotations

import datetime

from django.core import signing
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.ratelimit import TooMany, client_ip, too_many
from core.tenancy import rls_bypass
from members.models import Membership
from organizations.addresses import base_url
from organizations.imprint import ensure as ensure_imprint

from . import services
from .models import Survey, SurveyParticipation

SALT = "surveys.link"
GRACE = datetime.timedelta(days=30)
RATE = (60, 600)


def token(survey_id: int, membership_id: int) -> str:
    return signing.dumps({"s": survey_id, "m": membership_id}, salt=SALT, compress=True)


def parse(value: str) -> tuple[int, int] | None:
    try:
        data = signing.loads(value, salt=SALT)
    except signing.BadSignature:
        return None
    if not isinstance(data, dict):
        return None
    s, m = data.get("s"), data.get("m")
    if not isinstance(s, int) or not isinstance(m, int):
        return None
    return s, m


def url(survey: Survey, membership_id: int) -> str:
    return f"{base_url(survey.organization)}/umfrage/{token(survey.pk, membership_id)}"


def _no_store(response: Response) -> Response:
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


class PublicSurveyView(APIView):
    """GET: Umfrage, eigene Antwort, Ergebnis · POST: Antworten speichern."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def resolve(self, request, value: str, *, lock: bool = False):
        key = f"survey-link:{client_ip(request)}"
        if too_many(key, RATE[0], RATE[1]):
            raise TooMany(key, "aufrufe")
        ids = parse(value)
        invalid = gettext("Dieser Link ist ungültig oder abgelaufen.")
        if ids is None:
            raise NotFound(invalid)
        survey_id, membership_id = ids
        with rls_bypass():
            qs = Survey.objects.select_related("organization", "department", "event")
            if lock:
                qs = qs.select_for_update(of=("self",))
            survey = qs.filter(pk=survey_id).first()
            if (
                survey is None
                or "surveys" not in (survey.organization.enabled_modules or [])
                or survey.status == Survey.Status.DRAFT
                or (survey.closes_at and survey.closes_at + GRACE < timezone.now())
                or not services.is_eligible(survey, membership_id)
            ):
                raise NotFound(invalid)
            membership = Membership.objects.select_related("person", "organization").get(
                pk=membership_id
            )
        return survey, membership

    def data(self, survey: Survey, membership: Membership) -> dict:
        from .portal import survey_data

        with rls_bypass():
            row = survey_data(survey, membership.pk)
            imprint_key = ensure_imprint(survey.organization).public_key
        return {
            "club": survey.organization.name,
            "imprint_key": imprint_key,
            "first_name": membership.person.first_name,
            "survey": row,
        }

    def get(self, request, token: str):
        survey, membership = self.resolve(request, token)
        return _no_store(Response(self.data(survey, membership)))

    def post(self, request, token: str):
        deferred = []
        with transaction.atomic():
            survey, membership = self.resolve(request, token, lock=True)
            with rls_bypass():
                res = services.save_answers(
                    survey,
                    membership,
                    request.data.get("answers"),
                    source=SurveyParticipation.Source.LINK,
                    defer_anonymous_answers=True,
                )
                if isinstance(res, tuple):
                    _, deferred = res
        if deferred:
            with rls_bypass():
                services.store_anonymous_answers(deferred)
        return _no_store(Response(self.data(survey, membership)))
