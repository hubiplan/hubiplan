"""Erinnerung an eigene Dienste per Mail (Schritt H2).

Jede eingeteilte Person mit E-Mail-Adresse bekommt so viele Tage vor der Schicht, wie der
Plan vorsieht, eine Mail. Externe ohne Mitgliedschaft bekommen keine Mail.
"""

from __future__ import annotations

import datetime
import logging

from django.utils import timezone
from django.utils.translation import gettext as _

from core.i18n import date_text, language_of_org
from core.tenancy import rls_bypass
from organizations.addresses import base_url
from outbox import mail

from .models import HelperPlan, ShiftAssignment

logger = logging.getLogger(__name__)


def due(now: datetime.datetime) -> list[ShiftAssignment]:
    with rls_bypass():
        rows = (
            ShiftAssignment.objects.filter(
                status=ShiftAssignment.Status.ACTIVE,
                reminded_at__isnull=True,
                membership__isnull=False,
                shift__starts_at__gt=now,
                shift__starts_at__lte=now + datetime.timedelta(days=15),
                shift__duty__plan__status=HelperPlan.Status.PUBLISHED,
                shift__duty__plan__remind_days__isnull=False,
            )
            .select_related("shift__duty__plan__organization", "membership__person")
            .order_by("pk")
        )
        return [
            a
            for a in rows
            if a.shift.starts_at - datetime.timedelta(days=a.shift.duty.plan.remind_days) <= now
        ]


def text(assignment: ShiftAssignment) -> tuple[str, str]:
    shift = assignment.shift
    duty = shift.duty
    plan = duty.plan
    start = timezone.localtime(shift.starts_at)
    end = timezone.localtime(shift.ends_at)
    when = f"{date_text(start)}, {start:%H:%M}–{end:%H:%M}"
    subject = _("Erinnerung: {duty} am {day}").format(duty=duty.name, day=date_text(start))
    lines = [
        _("Hallo {name},").format(name=assignment.membership.person.first_name),
        "",
        _("eine Erinnerung an deinen Dienst:"),
        "",
        f"{duty.name} · {plan.title}",
        _("Wann: {when}").format(when=when),
    ]
    if duty.location:
        lines.append(_("Wo: {place}").format(place=duty.location))
    if shift.note:
        lines.append(shift.note)
    lines += [
        "",
        _("Deine Dienste siehst du im Mitgliederbereich: {url}").format(
            url=f"{base_url(plan.organization)}/mein-bereich/helferdienste"
        ),
        "",
        plan.organization.name,
    ]
    return subject, "\n".join(lines) + "\n"


def send_reminders(now: datetime.datetime | None = None) -> int:
    from events.rsvp import email_of

    now = now or timezone.now()
    sent = 0
    for assignment in due(now):
        with rls_bypass():
            # Erst vermerken, dann senden: lieber eine Erinnerung zu wenig als doppelt
            claimed = ShiftAssignment.objects.filter(
                pk=assignment.pk, reminded_at__isnull=True
            ).update(reminded_at=now)
            if not claimed:
                continue
            address = email_of(assignment.membership)
            if not address:
                continue
            org = assignment.shift.duty.plan.organization
            with language_of_org(org):
                subject, body = text(assignment)
            sent += int(
                mail.send(
                    address,
                    subject,
                    body,
                    organization=org,
                    kind="helferdienst",
                    fail_silently=True,
                )
            )
    logger.info("Helferdienste: %s Erinnerungen", sent)
    return sent
