"""Bescheid zu Umfragen: beim Start und als Erinnerung vor dem Ende (UM-8).

Wer die App mit Push nutzt, bekommt einen Push, alle anderen mit E-Mail-Adresse eine Mail mit
einem Link, über den sie ohne Anmeldung antworten. Briefe gibt es nicht.
"""

from __future__ import annotations

import datetime
import logging

from django.utils import timezone
from django.utils.translation import gettext as _

from core.i18n import datetime_text, language_of_org
from core.tenancy import rls_bypass
from outbox import mail

from . import link, services
from .models import Survey, SurveyParticipation

logger = logging.getLogger(__name__)

START = "start"
REMIND = "remind"


def owner(survey: Survey) -> str:
    return survey.department.name if survey.department_id else survey.organization.name


def subject(survey: Survey, kind: str) -> str:
    if kind == REMIND:
        return _("Erinnerung: Umfrage „{title}“").format(title=survey.title)
    return _("Umfrage: {title}").format(title=survey.title)


def body(survey: Survey, kind: str, first_name: str, url: str) -> str:
    lines = [_("Hallo {name},").format(name=first_name), ""]
    if kind == REMIND:
        lines.append(_("du hast die folgende Umfrage noch nicht beantwortet:"))
    else:
        lines.append(_("{owner} bittet dich um deine Meinung:").format(owner=owner(survey)))
    lines += ["", survey.title]
    if survey.description:
        lines += ["", survey.description]
    if survey.closes_at:
        lines += ["", _("Antworten bis: {when}").format(when=datetime_text(survey.closes_at))]
    if survey.anonymous:
        lines += ["", _("Die Umfrage ist anonym. Niemand sieht, was du geantwortet hast.")]
    lines += [
        "",
        _("Zur Umfrage: {url}").format(url=url),
        "",
        _("Ein Meinungsbild, kein Beschluss."),
        "",
        survey.organization.name,
    ]
    return "\n".join(lines) + "\n"


def push_data(survey: Survey, kind: str) -> dict:
    data = {
        "v": 1,
        "t": "survey",
        "id": survey.pk,
        "kind": kind,
        "title": subject(survey, kind)[:200],
        "from": owner(survey)[:200],
    }
    if survey.closes_at:
        data["text"] = _("Antworten bis {when}").format(when=datetime_text(survey.closes_at))
    return data


def send(survey_id: int, kind: str) -> int:
    """Bescheid an alle Befragten (Erinnerung: nur an die ohne Antwort)."""
    from devices.push import app_accesses, send_to_user
    from events.rsvp import email_of
    from portal.models import PortalAccess

    with rls_bypass():
        survey = (
            Survey.objects.select_related("organization", "department", "event")
            .filter(pk=survey_id)
            .first()
        )
        if survey is None or not services.is_open(survey):
            return 0
        ids = services.eligible_ids(survey)
        if kind == REMIND:
            done = set(
                SurveyParticipation.objects.filter(survey=survey).values_list(
                    "membership_id", flat=True
                )
            )
            ids = [i for i in ids if i not in done]
        accesses = app_accesses(ids)
        users = dict(
            PortalAccess.objects.filter(pk__in=accesses.values()).values_list("pk", "user_id")
        )
        sent = 0
        pushed_members = set()
        with language_of_org(survey.organization):
            base = push_data(survey, kind)
        for membership_id, access_id in accesses.items():
            user_id = users.get(access_id)
            if user_id and send_to_user(user_id, {**base, "access": access_id}) > 0:
                pushed_members.add(membership_id)
                sent += 1
        rest = [i for i in ids if i not in pushed_members]
        from members.models import Membership

        for membership in Membership.objects.filter(pk__in=rest).select_related(
            "person", "organization"
        ):
            address = email_of(membership)
            if not address:
                continue
            with language_of_org(survey.organization):
                text = body(
                    survey, kind, membership.person.first_name, link.url(survey, membership.pk)
                )
                title = subject(survey, kind)
            mail_kind = (
                "umfrage_anonym"
                if kind == REMIND and survey.anonymity == Survey.Anonymity.ANONYMOUS
                else "umfrage"
            )
            sent += int(
                mail.send(
                    address,
                    title,
                    text,
                    organization=survey.organization,
                    kind=mail_kind,
                    fail_silently=True,
                )
            )
    logger.info("Umfrage %s: %s Bescheide (%s)", survey_id, sent, kind)
    return sent


def due_reminders(now: datetime.datetime | None = None) -> list[int]:
    now = now or timezone.now()
    with rls_bypass():
        rows = Survey.objects.filter(
            status=Survey.Status.OPEN,
            remind_days__isnull=False,
            reminded_at__isnull=True,
            closes_at__gt=now,
        ).values_list("pk", "closes_at", "remind_days")
        return [pk for pk, end, days in rows if end - datetime.timedelta(days=days) <= now]


def send_reminders(now: datetime.datetime | None = None) -> int:
    now = now or timezone.now()
    total = 0
    for pk in due_reminders(now):
        with rls_bypass():
            claimed = Survey.objects.filter(pk=pk, reminded_at__isnull=True).update(reminded_at=now)
        if claimed:
            total += send(pk, REMIND)
    return total
