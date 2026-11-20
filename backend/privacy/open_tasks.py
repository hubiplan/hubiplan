"""Offene Datenpannen unter „Zu erledigen“ für alle, die die Datenschutz-Werkzeuge pflegen."""

from __future__ import annotations

from django.utils import timezone
from django.utils.translation import gettext

from .access import EDIT
from .services import breach_status, open_breaches


def breach_tasks(org, perms: set[str]) -> list[dict]:
    if EDIT not in perms or org.type not in ("club", "federation"):
        return []
    now = timezone.now()
    items = []
    for b in open_breaches(org):
        status = breach_status(b, now)
        deadline = timezone.localtime(b.report_deadline)
        if status == "overdue":
            detail = gettext("Meldefrist abgelaufen am {date}")
        elif status == "report_due":
            detail = gettext("Meldung an die Aufsichtsbehörde bis {date}")
        else:
            detail = gettext("noch nicht abgeschlossen")
        items.append(
            {
                "kind": "breach",
                "area": "privacy",
                "kind_label": gettext("Datenpanne"),
                "title": b.title,
                "detail": detail.format(date=f"{deadline:%d.%m.%Y %H:%M}"),
                "created_at": b.created_at,
                "ref": b.pk,
                "link": f"/dsgvo/datenpannen?panne={b.pk}",
                "highlight": status in ("overdue", "report_due"),
            }
        )
    return items
