"""Meldungen unter „Zu erledigen“ (Menüprüfung 2, N-03): Rückfrage des Veranstalters und
begonnene eigene Meldungen, deren Meldeschluss bald ist. Nur mit dem Recht, Meldungen abzugeben."""

from __future__ import annotations

import datetime

from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext

from access.catalog import ENTRIES_MANAGE, ENTRIES_SUBMIT

from .models import Call, Entry

# Meldeschluss in so vielen Tagen
DEADLINE_DAYS = 7


def entry_tasks(org, perms: set[str]) -> list[dict]:
    if not ({ENTRIES_SUBMIT, ENTRIES_MANAGE} & perms) or "entries" not in (
        org.enabled_modules or []
    ):
        return []
    if org.type not in ("club", "federation"):
        return []
    today = timezone.localdate()
    short = lambda day: date_format(day, "SHORT_DATE_FORMAT", use_l10n=True)  # noqa: E731
    items: list[dict] = []
    returned = Entry.objects.filter(
        organization=org, department__isnull=True, status=Entry.Status.RETURNED
    ).select_related("call")
    for e in returned:
        items.append(
            {
                "kind": "entry_returned",
                "area": "entries",
                "kind_label": gettext("Meldung"),
                "title": gettext("Rückfrage zu „{title}“").format(title=e.call.title),
                "detail": e.call.organizer,
                "created_at": e.updated_at,
                "link": f"/meldungen/{e.call_id}",
                "highlight": True,
            }
        )
    soon = Call.objects.filter(
        organization=org,
        deadline__gte=today,
        deadline__lte=today + datetime.timedelta(days=DEADLINE_DAYS),
    ).order_by("deadline")
    own = {
        e.call_id: e.status
        for e in Entry.objects.filter(organization=org, department__isnull=True, call__in=soon)
    }
    for call in soon:
        # Nur begonnene Meldungen: Ausschreibungen, die nur an Untereinheiten gehen, haben
        # keine eigene Meldung; Rückfragen stehen schon oben
        if own.get(call.pk) != Entry.Status.DRAFT:
            continue
        items.append(
            {
                "kind": "entry_deadline",
                "area": "entries",
                "kind_label": gettext("Meldung"),
                "title": gettext("Meldung zu „{title}“ abgeben").format(title=call.title),
                "detail": gettext("Meldeschluss am {date}").format(date=short(call.deadline)),
                "created_at": call.deadline,
                "link": f"/meldungen/{call.pk}",
                "highlight": call.deadline <= today + datetime.timedelta(days=2),
            }
        )
    return items
