"""Zweckgebundene Spenden (Konzept vereinskasse-steuern, S5).

Eine Spende „für die neue Fahne“ darf nur für diesen Zweck verwendet werden. Spenden und
Ausgaben lassen sich einer Zweckbindung zuordnen; der Rest zeigt, was noch zweckgebunden
zu verwenden ist. Gezählt werden Geldzuwendungen und Ausgaben; Stornos und stornierte
Buchungen zählen nicht. Liegt die älteste Spende mit Rest mehr als zwei Jahre zurück, weist
die Übersicht auf die zeitnahe Mittelverwendung hin (§ 55 Abs. 1 Nr. 5 AO).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.db.models import Max, Min, Sum
from django.utils import timezone

from .models import Booking, Donation, Earmark

ZERO = Decimal("0.00")
TIMELY_YEARS = 2


def _donations(org) -> dict[int, dict]:
    rows = (
        Donation.objects.filter(organization=org, earmark__isnull=False, kind=Donation.Kind.MONEY)
        .values("earmark_id")
        .annotate(s=Sum("amount"), first=Min("date"), last=Max("date"))
        .order_by()
    )
    return {r["earmark_id"]: r for r in rows}


def _expenses(org) -> dict[int, Decimal]:
    rows = (
        Booking.objects.filter(
            organization=org,
            earmark__isnull=False,
            kind=Booking.Kind.EXPENSE,
            cancels__isnull=True,
            cancellation__isnull=True,
        )
        .values("earmark_id")
        .annotate(s=Sum("amount"))
        .order_by()
    )
    return {r["earmark_id"]: r["s"] or ZERO for r in rows}


def overview(org, today: datetime.date | None = None) -> list[dict]:
    today = today or timezone.localdate()
    donations = _donations(org)
    expenses = _expenses(org)
    out = []
    for earmark in Earmark.objects.filter(organization=org):
        d = donations.get(earmark.pk) or {}
        received = d.get("s") or ZERO
        used = expenses.get(earmark.pk, ZERO)
        rest = received - used
        first = d.get("first")
        overdue = bool(
            rest > 0 and first is not None and today.year - org.fiscal_year_of(first) > TIMELY_YEARS
        )
        out.append(
            {
                "id": earmark.pk,
                "name": earmark.name,
                "note": earmark.note,
                "is_active": earmark.is_active,
                "received": received,
                "used": used,
                "rest": rest,
                "first_donation": first,
                "last_donation": d.get("last"),
                "overdue": overdue,
            }
        )
    return out
