"""Aufwandsvergütungen an Ehrenamtliche (Konzept vereinskasse-steuern, S3).

Übungsleiterfreibetrag (§ 3 Nr. 26 EStG) und Ehrenamtspauschale (§ 3 Nr. 26a EStG) gelten je
Person und Kalenderjahr. Gezählt werden Ausgaben mit gesetzter Vergütungsart; stornierte
Buchungen und Stornos zählen nicht. Der Freibetrag gilt über alle Auftraggeber zusammen,
deshalb bestätigt der Empfänger schriftlich, dass er ihn nicht anderweitig nutzt.

Außerdem zählen:
- Aufwandsspenden aus dem Verzicht auf eine Pauschale: Der Anspruch gilt als zugeflossen und
  wird gespendet, verbraucht also den Freibetrag ebenso wie eine Auszahlung,
- Auszahlungen an Musiker aus der Musikerabrechnung (künstlerische Tätigkeit, § 3 Nr. 26),
  der Person des Musikers zugeordnet,
- Zahlungen der Untereinheiten mit eigener Kasse, die steuerlich zum Verein gehören. Personen
  werden über ihre Akte erkannt, damit dieselbe Person in Verein und Untereinheit nur einmal
  erscheint.
"""

from __future__ import annotations

import datetime
import hashlib
from decimal import Decimal

from django.db.models import Q
from django.utils.translation import gettext

from .models import Booking, Donation

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


def _free_text(name: str) -> tuple[str, str]:
    digest = hashlib.sha256(name.strip().casefold().encode()).hexdigest()[:12]
    return f"n{digest}", name.strip()


def _membership_key(membership) -> tuple[str, str]:
    return f"p{membership.person_id}", membership.person.display_name


def _key(booking: Booking) -> tuple[str, str, object]:
    """Schlüssel, Name und Mitgliedschaft der Person: Musiker der Musikerabrechnung,
    sonst das Mitglied, sonst der Empfänger als Freitext."""
    expense = getattr(booking, "performance_expense", None)
    musician = expense.claim.assignment.musician if expense and expense.claim_id else None
    if musician is not None:
        if musician.membership_id:
            return (*_membership_key(musician.membership), musician.membership)
        if musician.name:
            return (*_free_text(musician.name), None)
    if booking.membership_id:
        return (*_membership_key(booking.membership), booking.membership)
    return (*_free_text(booking.counterparty), None)


def _donation_key(donation: Donation) -> tuple[str, str, object]:
    if donation.membership_id:
        return (*_membership_key(donation.membership), donation.membership)
    return (*_free_text(donation.donor_name), None)


def _board_people(orgs, year: int) -> set[int]:
    """Personen (Akten) mit Vorstandsrolle irgendwann im Kalenderjahr."""
    from access.models import RoleAssignment

    first, last = datetime.date(year, 1, 1), datetime.date(year, 12, 31)
    return set(
        RoleAssignment.objects.filter(
            organization__in=orgs,
            role__is_board=True,
            person__isnull=False,
            valid_from__lte=last,
        )
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=first))
        .values_list("person_id", flat=True)
    )


def _orgs(org):
    """Einheiten, deren Zahlungen zusammengezählt werden, und die zusammenrechnende Einheit.

    Wie in der steuerlichen Auswertung sieht nur die zusammenrechnende Einheit die Zahlen
    ihrer Untereinheiten; eine Untereinheit sieht ihre eigenen."""
    from .tax import tax_root, tax_units

    root = tax_root(org)
    if root.pk != org.pk:
        return [org], root
    return [org, *tax_units(org)], root


def _active(qs):
    return qs.filter(cancels__isnull=True, cancellation__isnull=True)


def bookings(orgs, year: int):
    return (
        _active(
            Booking.objects.filter(
                organization__in=orgs, kind=Booking.Kind.EXPENSE, date__year=year
            )
        )
        .exclude(allowance="")
        .select_related(
            "membership__person",
            "organization",
            "performance_expense__claim__assignment__musician__membership__person",
        )
        .order_by("date", "organization_id", "number")
    )


def waivers(orgs, year: int):
    """Aufwandsspenden aus dem Verzicht auf eine Pauschale."""
    return (
        Donation.objects.filter(organization__in=orgs, waiver=True, date__year=year)
        .exclude(allowance="")
        .select_related("membership__person", "organization")
        .order_by("date", "pk")
    )


def _music_unassigned(orgs, year: int) -> dict | None:
    """Auszahlungen aus der Musikerabrechnung ohne gewählte Vergütungsart."""
    rows = list(
        _active(
            Booking.objects.filter(
                organization__in=orgs,
                kind=Booking.Kind.EXPENSE,
                date__year=year,
                allowance="",
                performance_expense__claim__isnull=False,
            )
        ).values_list("amount", flat=True)
    )
    if not rows:
        return None
    return {"count": len(rows), "total": sum(rows, Decimal("0"))}


def report(org, year: int) -> dict:
    limit = limits(year)
    orgs, root = _orgs(org)
    board = _board_people(orgs, year)
    people: dict[str, dict] = {}

    def add(key, name, membership, kind, row):
        person = people.setdefault(
            key,
            {
                "key": key,
                "name": name,
                "membership": membership.pk if membership else None,
                "board": bool(membership and membership.person_id in board),
                "totals": {},
                "bookings": [],
            },
        )
        person["totals"][kind] = person["totals"].get(kind, Decimal("0")) + row["amount"]
        person["bookings"].append({**row, "allowance": kind})

    for b in bookings(orgs, year):
        key, name, membership = _key(b)
        add(
            key,
            name,
            membership,
            b.allowance,
            {
                "id": b.id,
                "source": "booking",
                "display_number": b.display_number,
                "date": b.date,
                "amount": b.amount,
                "text": b.text,
                "unit": b.organization.name if b.organization_id != org.pk else "",
            },
        )
    for d in waivers(orgs, year):
        key, name, membership = _donation_key(d)
        add(
            key,
            name,
            membership,
            d.allowance,
            {
                "id": d.id,
                "source": "waiver",
                "display_number": gettext("Verzicht (Aufwandsspende)"),
                "date": d.date,
                "amount": d.amount,
                "text": d.note,
                "unit": d.organization.name if d.organization_id != org.pk else "",
            },
        )
    for person in people.values():
        person["bookings"].sort(key=lambda r: r["date"])
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
    music = _music_unassigned(orgs, year)
    if music:
        warnings.append(
            {
                "kind": "music",
                "text": gettext(
                    "{n} Auszahlungen aus der Musikerabrechnung über {x} € haben keine "
                    "Vergütungsart. Musiker können den Übungsleiterfreibetrag nutzen "
                    "(künstlerische Tätigkeit, § 3 Nr. 26 EStG); bitte die Buchungen im "
                    "Kassenbuch prüfen."
                ).format(n=music["count"], x=f"{music['total']:.2f}".replace(".", ",")),
            }
        )
    return {
        "year": year,
        "limits": limit,
        "units": [u.name for u in orgs[1:]],
        "counted_at": root.name if root.pk != org.pk else "",
        "board_pay_allowed": org.board_pay_allowed,
        "people": rows,
        "warnings": warnings,
    }


def person(data: dict, key: str) -> dict | None:
    return next((p for p in data["people"] if p["key"] == key), None)
