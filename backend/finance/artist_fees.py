"""Künstlersozialabgabe (Konzept vereinskasse-steuern, S4).

Wer regelmäßig selbständige Künstler oder Publizisten bezahlt (Kapelle, Tambourcorps, DJ,
Grafiker), meldet die Honorare eines Kalenderjahres bis zum 31. März des Folgejahres an die
Künstlersozialkasse. Gezählt werden Ausgaben, die als Künstlerhonorar gekennzeichnet sind
oder deren Kategorie so markiert ist; Stornos und stornierte Buchungen zählen nicht.
Bemessungsgrundlage sind die Entgelte ohne gesondert ausgewiesene Umsatzsteuer.
"""

from __future__ import annotations

import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q

from .models import Booking

# (ab Jahr, Abgabesatz in Prozent)
RATES = (
    (2027, Decimal("5.0")),
    (2026, Decimal("4.9")),
    (2023, Decimal("5.0")),
    (2021, Decimal("4.2")),
    (0, Decimal("4.2")),
)
# § 24 Abs. 3 KSVG: Bei Veranstaltungen und Eigenwerbung keine Abgabepflicht, solange die
# Entgelte im Kalenderjahr 450 € nicht übersteigen (seit 2023)
THRESHOLD = Decimal("450")


def rate(year: int) -> Decimal:
    for since, value in RATES:
        if year >= since:
            return value
    raise AssertionError  # pragma: no cover


def bookings(org, year: int):
    return (
        Booking.objects.filter(
            organization=org,
            kind=Booking.Kind.EXPENSE,
            date__year=year,
            cancels__isnull=True,
            cancellation__isnull=True,
        )
        .filter(Q(artist_fee=True) | Q(category__artist_fees=True) | Q(partner__artist=True))
        .select_related("organization", "category", "membership__person")
        .order_by("date", "number")
    )


def _name(b: Booking) -> str:
    if b.counterparty:
        return b.counterparty
    if b.membership_id:
        return b.membership.person.display_name
    return ""


def report(org, year: int) -> dict:
    people: dict[str, dict] = {}
    rows = []
    total = Decimal("0")
    for b in bookings(org, year):
        name = _name(b)
        entry = people.setdefault(
            name.casefold(), {"name": name, "total": Decimal("0"), "count": 0}
        )
        entry["total"] += b.amount
        entry["count"] += 1
        total += b.amount
        rows.append(
            {
                "id": b.id,
                "display_number": b.display_number,
                "date": b.date,
                "amount": b.amount,
                "text": b.text,
                "name": name,
                "category": b.frozen_category_name or (b.category.name if b.category else ""),
            }
        )
    percent = rate(year)
    levy = (total * percent / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "year": year,
        "rate": percent,
        "threshold": THRESHOLD,
        "total": total,
        "levy": levy,
        "over_threshold": total > THRESHOLD,
        "due": datetime.date(year + 1, 3, 31),
        "recipients": sorted(people.values(), key=lambda p: p["name"].casefold()),
        "bookings": rows,
    }
