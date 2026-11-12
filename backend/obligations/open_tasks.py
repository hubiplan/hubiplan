"""Fällige Pflichten unter „Zu erledigen“: für alle, die den Fristenkalender pflegen,
und für die Inhaber der zuständigen Rolle."""

from __future__ import annotations

from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext

from .access import EDIT, MODULE, VIEW
from .services import due_soon, holds_role


def obligation_tasks(user, org, perms: set[str]) -> list[dict]:
    if VIEW not in perms or MODULE not in (org.enabled_modules or []):
        return []
    if org.type not in ("club", "federation"):
        return []
    today = timezone.localdate()
    items = []
    for o in due_soon(org, today):
        if EDIT not in perms and not holds_role(user, o):
            continue
        day = date_format(o.due_date, "SHORT_DATE_FORMAT", use_l10n=True)
        overdue = o.due_date < today
        items.append(
            {
                "kind": "obligation",
                "area": "obligations",
                "kind_label": gettext("Fristenkalender"),
                "title": o.title,
                "detail": (
                    gettext("überfällig seit {date}") if overdue else gettext("Frist {date}")
                ).format(date=day),
                "created_at": o.created_at,
                "ref": o.pk,
                "link": f"/fristenkalender?pflicht={o.pk}",
                "highlight": overdue or (o.due_date - today).days <= 7,
            }
        )
    return items
