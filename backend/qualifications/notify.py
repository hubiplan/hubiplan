"""Erinnerung vor dem Ablauf einer Qualifikation (per Mail an das Mitglied).

So viele Tage vor dem Ablauf, wie die Art vorsieht, bekommt das Mitglied einmal eine Mail.
Nur der maßgebliche (am längsten gültige) Nachweis zählt: Ist schon verlängert, kommt keine
Erinnerung. Den Vorstand erinnert die Liste „Zu erledigen“ (open_tasks.py).
"""

from __future__ import annotations

import datetime
import logging

from django.utils import timezone
from django.utils.translation import gettext as _

from core.i18n import date_text, language_of_org
from core.tenancy import rls_bypass
from outbox import mail

from . import services
from .models import Qualification

logger = logging.getLogger(__name__)

# Höchstens so weit voraus wird gesucht (größter Vorlauf einer Art)
HORIZON_DAYS = 366


def due(on: datetime.date) -> list[tuple[Qualification, object]]:
    """(Nachweis, Mitgliedschaft) mit fälliger Erinnerung."""
    from members.views import member_queryset
    from organizations.models import Organization

    result = []
    with rls_bypass():
        candidates = (
            Qualification.objects.filter(
                reminded_at__isnull=True,
                valid_until__isnull=False,
                valid_until__gte=on,
                valid_until__lte=on + datetime.timedelta(days=HORIZON_DAYS),
                kind__remind_days__isnull=False,
                kind__is_archived=False,
            )
            .select_related("kind", "person")
            .order_by("organization_id", "pk")
        )
        by_org: dict[int, list[Qualification]] = {}
        for q in candidates:
            if q.valid_until - datetime.timedelta(days=q.kind.remind_days) <= on:
                by_org.setdefault(q.organization_id, []).append(q)
        for org in Organization.objects.filter(pk__in=list(by_org)):
            if not services.module_on(org):
                continue
            rows = by_org[org.pk]
            person_ids = {q.person_id for q in rows}
            members = {
                m.person_id: m
                for m in member_queryset(org)
                .filter(person_id__in=person_ids, is_current=True, purged_at__isnull=True)
                .select_related("person", "organization")
            }
            best = services.current_for(org.pk, person_ids, {q.kind_id for q in rows})
            for q in rows:
                if q.person_id not in members:
                    continue
                if best.get((q.person_id, q.kind_id)) != q:
                    continue  # schon verlängert
                result.append((q, members[q.person_id]))
    return result


def text(q: Qualification, membership) -> tuple[str, str]:
    org = membership.organization
    subject = _("Erinnerung: „{name}“ läuft am {date} ab").format(
        name=q.kind.name, date=date_text(q.valid_until)
    )
    lines = [
        _("Hallo {name},").format(name=membership.person.first_name),
        "",
        _("dein Nachweis „{name}“ ist laut unseren Unterlagen bis {date} gültig.").format(
            name=q.kind.name, date=date_text(q.valid_until)
        ),
        _(
            "Bitte denk rechtzeitig an die Verlängerung und gib dem Vorstand Bescheid, "
            "sobald du den neuen Nachweis hast."
        ),
        "",
        org.name,
    ]
    return subject, "\n".join(lines) + "\n"


def send_reminders(now: datetime.datetime | None = None) -> int:
    from events.rsvp import email_of

    now = now or timezone.now()
    sent = 0
    for q, membership in due(timezone.localdate(now)):
        with rls_bypass():
            # Erst vermerken, dann senden: lieber eine Erinnerung zu wenig als doppelt
            claimed = Qualification.objects.filter(pk=q.pk, reminded_at__isnull=True).update(
                reminded_at=now
            )
            if not claimed:
                continue
            address = email_of(membership)
            if not address:
                continue
            org = membership.organization
            with language_of_org(org):
                subject, body = text(q, membership)
            sent += int(
                mail.send(
                    address,
                    subject,
                    body,
                    organization=org,
                    kind="qualifikation",
                    fail_silently=True,
                )
            )
    logger.info("Qualifikationen: %s Erinnerungen", sent)
    return sent
