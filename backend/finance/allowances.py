"""Aufwandsvergütungen an Ehrenamtliche (Konzept vereinskasse-steuern, S3).

Übungsleiterfreibetrag (§ 3 Nr. 26 EStG) und Ehrenamtspauschale (§ 3 Nr. 26a EStG) gelten je
Person und Kalenderjahr. Gezählt werden Ausgaben mit gesetzter Vergütungsart; stornierte
Buchungen und Stornos zählen nicht. Der Freibetrag gilt über alle Auftraggeber zusammen,
deshalb bestätigt der Empfänger schriftlich, dass er ihn nicht anderweitig nutzt.
"""

from __future__ import annotations

import datetime
import hashlib
from decimal import Decimal

from django.db.models import Q
from django.utils.translation import gettext

from .models import Booking

TRAINER = Booking.Allowance.TRAINER
VOLUNTEER = Booking.Allowance.VOLUNTEER

# (ab Jahr, Übungsleiterfreibetrag, Ehrenamtspauschale)
LIMITS = (
    (2026, Decimal("3300"), Decimal("960")),  # Steueränderungsgesetz 2025
    (2021, Decimal("3000"), Decimal("840")),  # Jahressteuergesetz 2020
    (0, Decimal("2400"), Decimal("720")),
)
WARN_FROM = Decimal("0.8")


def limits(year: int) -> dict[str, Decimal]:
    for since, trainer, volunteer in LIMITS:
        if year >= since:
            return {TRAINER: trainer, VOLUNTEER: volunteer}
    raise AssertionError  # pragma: no cover


def _status(total: Decimal, limit: Decimal) -> str:
    if total > limit:
        return "over"
    if total >= limit * WARN_FROM:
        return "warn"
    return "ok"


def _key(booking: Booking) -> tuple[str, str]:
    """Schlüssel und Name der Person: Mitglied, sonst der Empfänger als Freitext."""
    if booking.membership_id:
        return f"m{booking.membership_id}", booking.membership.person.display_name
    name = booking.counterparty
    digest = hashlib.sha256(name.casefold().encode()).hexdigest()[:12]
    return f"n{digest}", name


def _board_people(org, year: int) -> set[int]:
    """Personen (Akten) mit Vorstandsrolle irgendwann im Kalenderjahr."""
    from access.models import RoleAssignment

    first, last = datetime.date(year, 1, 1), datetime.date(year, 12, 31)
    return set(
        RoleAssignment.objects.filter(
            organization=org,
            role__is_board=True,
            person__isnull=False,
            valid_from__lte=last,
        )
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=first))
        .values_list("person_id", flat=True)
    )


def bookings(org, year: int):
    return (
        Booking.objects.filter(
            organization=org,
            kind=Booking.Kind.EXPENSE,
            date__year=year,
            cancels__isnull=True,
            cancellation__isnull=True,
        )
        .exclude(allowance="")
        .select_related("membership__person", "organization")
        .order_by("date", "number")
    )


def report(org, year: int) -> dict:
    limit = limits(year)
    board = _board_people(org, year)
    people: dict[str, dict] = {}
    for b in bookings(org, year):
        key, name = _key(b)
        person = people.setdefault(
            key,
            {
                "key": key,
                "name": name,
                "membership": b.membership_id,
                "board": bool(b.membership_id and b.membership.person_id in board),
                "totals": {},
                "bookings": [],
            },
        )
        person["totals"][b.allowance] = person["totals"].get(b.allowance, Decimal("0")) + b.amount
        person["bookings"].append(
            {
                "id": b.id,
                "display_number": b.display_number,
                "date": b.date,
                "amount": b.amount,
                "allowance": b.allowance,
                "text": b.text,
            }
        )
    rows = []
    for person in sorted(people.values(), key=lambda p: p["name"].casefold()):
        kinds = []
        for kind in (TRAINER, VOLUNTEER):
            total = person["totals"].get(kind)
            if total is None:
                continue
            kinds.append(
                {
                    "kind": kind,
                    "label": str(Booking.Allowance(kind).label),
                    "total": total,
                    "limit": limit[kind],
                    "percent": int(total * 100 / limit[kind]),
                    "status": _status(total, limit[kind]),
                }
            )
        person["kinds"] = kinds
        person["board_warning"] = person["board"] and not org.board_pay_allowed
        del person["totals"]
        rows.append(person)
    warnings = []
    if any(p["board_warning"] for p in rows):
        warnings.append(
            {
                "kind": "board",
                "text": gettext(
                    "Vorstandsmitglieder erhalten eine Vergütung, obwohl nicht eingetragen ist, "
                    "dass die Satzung das erlaubt. Ohne Satzungsregelung ist der Vorstand "
                    "unentgeltlich tätig (§ 27 Abs. 3 BGB), und die Gemeinnützigkeit kann "
                    "gefährdet sein."
                ),
            }
        )
    if any(k["status"] == "over" for p in rows for k in p["kinds"]):
        warnings.append(
            {
                "kind": "over",
                "text": gettext(
                    "Über dem Freibetrag ist die Vergütung steuer- und meist "
                    "sozialversicherungspflichtig (z. B. als Minijob). Bitte mit der "
                    "Steuerberatung bzw. Lohnabrechnung klären."
                ),
            }
        )
    return {
        "year": year,
        "limits": limit,
        "board_pay_allowed": org.board_pay_allowed,
        "people": rows,
        "warnings": warnings,
    }


def person(data: dict, key: str) -> dict | None:
    return next((p for p in data["people"] if p["key"] == key), None)
