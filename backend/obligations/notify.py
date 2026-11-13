"""Erinnerung an fällige Pflichten per Mail an die Inhaber der zuständigen Rolle.

Einmal je Frist, sobald der Erinnerungszeitraum beginnt. Ohne zuständige Rolle bekommen
alle die Mail, die den Fristenkalender pflegen dürfen.
"""

from __future__ import annotations

import datetime
import logging

from django.db.models import F, Q
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from core.i18n import date_text, user_language
from core.tenancy import rls_bypass
from organizations.addresses import base_url
from outbox import mail

from .access import MODULE
from .models import Obligation
from .services import responsible_users

logger = logging.getLogger(__name__)


def due(today: datetime.date) -> list[Obligation]:
    with rls_bypass():
        rows = (
            Obligation.objects.filter(
                active=True,
                trigger=Obligation.Trigger.DATE,
                due_date__isnull=False,
                due_date__lte=today + datetime.timedelta(days=366),
                organization__is_active=True,
            )
            .filter(Q(reminded_for__isnull=True) | ~Q(reminded_for=F("due_date")))
            .select_related("organization", "role")
            .order_by("pk")
        )
        return [
            o
            for o in rows
            if o.due_date - datetime.timedelta(days=o.remind_days) <= today
            and MODULE in (o.organization.enabled_modules or [])
        ]


def text(obligation: Obligation, user, today: datetime.date) -> tuple[str, str]:
    org = obligation.organization
    overdue = obligation.due_date < today
    subject = (
        _("Überfällig: {title} (Frist {day})") if overdue else _("Erinnerung: {title} bis {day}")
    ).format(title=obligation.title, day=date_text(obligation.due_date))
    lines = [
        _("Hallo {name},").format(name=user.first_name or user.email),
        "",
        _("im Fristenkalender von {org} steht eine Pflicht an:").format(org=org.name),
        "",
        obligation.title,
        _("Frist: {day}").format(day=date_text(obligation.due_date)),
    ]
    if obligation.role_id:
        lines.append(_("Zuständig: {role}").format(role=obligation.role.name))
    if obligation.note:
        lines += ["", obligation.note]
    lines += [
        "",
        _("Wenn es erledigt ist, vermerke es bitte im Fristenkalender: {url}").format(
            url=f"{base_url(org)}/fristenkalender?pflicht={obligation.pk}"
        ),
        "",
        org.name,
    ]
    return subject, "\n".join(lines) + "\n"


def send_reminders(today: datetime.date | None = None) -> int:
    today = today or timezone.localdate()
    sent = 0
    for obligation in due(today):
        with rls_bypass():
            # Erst vermerken, dann senden: lieber eine Erinnerung zu wenig als doppelt
            claimed = (
                Obligation.objects.filter(pk=obligation.pk, due_date=obligation.due_date)
                .exclude(reminded_for=obligation.due_date)
                .update(reminded_for=obligation.due_date)
            )
            if not claimed:
                continue
            for user in responsible_users(obligation, today):
                if not user.email:
                    continue
                with translation.override(user_language(user)):
                    subject, body = text(obligation, user, today)
                sent += int(
                    mail.send(
                        user.email,
                        subject,
                        body,
                        organization=obligation.organization,
                        kind="fristenkalender",
                        fail_silently=True,
                    )
                )
    logger.info("Fristenkalender: %s Erinnerungen", sent)
    return sent
