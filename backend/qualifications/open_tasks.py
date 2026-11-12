"""Qualifikationen unter „Zu erledigen“: abgelaufene und bald ablaufende Nachweise
aktueller Mitglieder, je Art eine Zeile. Nur mit dem Recht, Mitglieder zu bearbeiten."""

from __future__ import annotations

from django.utils import timezone
from django.utils.translation import gettext, ngettext

from access.catalog import MEMBERS_EDIT

from . import services
from .models import Qualification


def qualification_tasks(org, perms: set[str]) -> list[dict]:
    from members.models import today
    from members.views import member_queryset

    if MEMBERS_EDIT not in perms or not services.module_on(org) or not org.keeps_members:
        return []
    person_ids = list(
        member_queryset(org)
        .filter(is_current=True, purged_at__isnull=True)
        .values_list("person_id", flat=True)
    )
    rows = Qualification.objects.filter(
        organization=org, person_id__in=person_ids, kind__is_archived=False
    ).select_related("kind")
    on = today()
    counts: dict[int, dict] = {}
    for q in services.latest(rows).values():
        state = services.status(q, on)
        if state == services.VALID:
            continue
        row = counts.setdefault(q.kind_id, {"kind": q.kind, "expired": 0, "expiring": 0})
        row[state] += 1
    items = []
    for row in counts.values():
        parts = []
        if row["expired"]:
            parts.append(
                ngettext("{n} abgelaufen", "{n} abgelaufen", row["expired"]).format(
                    n=row["expired"]
                )
            )
        if row["expiring"]:
            parts.append(
                ngettext("{n} läuft bald ab", "{n} laufen bald ab", row["expiring"]).format(
                    n=row["expiring"]
                )
            )
        items.append(
            {
                "kind": "qualifications_due",
                "kind_label": gettext("Qualifikationen"),
                "title": row["kind"].name,
                "detail": ", ".join(parts),
                "created_at": timezone.now(),
                "link": f"/mitglieder/qualifikationen?stand=bald&art={row['kind'].pk}",
                "highlight": bool(row["expired"]),
            }
        )
    return items
