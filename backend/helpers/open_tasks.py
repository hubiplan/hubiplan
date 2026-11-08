"""Helferdienste unter „Zu erledigen“ (Menüprüfung 2, N-03): veröffentlichte Pläne mit
offenen Plätzen in Schichten der nächsten Tage. Nur für die Einheit selbst und nur mit
dem Recht, Helferdienste zu bearbeiten."""

from __future__ import annotations

import datetime

from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext, ngettext

from .access import EDIT, MODULE
from .models import HelperPlan, Shift
from .services import free

# Schichten, die so bald beginnen, zählen
SOON_DAYS = 14


def helper_tasks(org, perms: set[str]) -> list[dict]:
    if EDIT not in perms or MODULE not in (org.enabled_modules or []):
        return []
    if org.type not in ("club", "federation"):
        return []
    now = timezone.now()
    shifts = (
        Shift.objects.filter(
            organization=org,
            duty__plan__department__isnull=True,
            duty__plan__status=HelperPlan.Status.PUBLISHED,
            starts_at__gte=now,
            starts_at__lt=now + datetime.timedelta(days=SOON_DAYS),
        )
        .select_related("duty__plan")
        .order_by("starts_at")
    )
    plans: dict[int, dict] = {}
    for shift in shifts:
        n = free(shift)
        if n <= 0:
            continue
        plan = shift.duty.plan
        row = plans.setdefault(
            plan.pk, {"plan": plan, "free": 0, "first": timezone.localtime(shift.starts_at)}
        )
        row["free"] += n
    return [
        {
            "kind": "helpers_open",
            "area": "helpers",
            "kind_label": gettext("Helferdienste"),
            "title": ngettext(
                "{title}: {n} Platz offen", "{title}: {n} Plätze offen", row["free"]
            ).format(title=row["plan"].title, n=row["free"]),
            "detail": gettext("erste offene Schicht am {date}").format(
                date=date_format(row["first"].date(), "SHORT_DATE_FORMAT", use_l10n=True)
            ),
            "created_at": row["first"],
            "link": f"/helferdienste?plan={row['plan'].pk}",
        }
        for row in plans.values()
    ]
