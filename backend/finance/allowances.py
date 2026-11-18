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

Unter dem Zeilenschutz sieht der Verein die Kasse einer Untereinheit nicht, und die
Untereinheit sieht die Mitgliedschaften des Vereins nicht. Deshalb wird jede Untereinheit in
ihrem eigenen Bereich gelesen (wie in der steuerlichen Auswertung) und dort nur die Nummer der
Mitgliedschaft gemerkt; Mitgliedschaft und Akte werden danach im Bereich der Mitgliedschaften
aufgelöst (Gesamtaudit 15.11., AZ-04).
"""

from __future__ import annotations

import datetime
import hashlib
from decimal import Decimal

from django.db.models import Q
from django.utils.translation import gettext

from core.tenancy import tenant_context, unit_context

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


def _booking_entry(booking: Booking, org) -> dict:
    """Eine Zahlung als einfache Daten, ohne Mitgliedschaft und Akte zu laden.

    Person: der Musiker der Musikerabrechnung, sonst das Mitglied der Buchung, sonst der
    Empfänger als Freitext."""
    expense = getattr(booking, "performance_expense", None)
    musician = expense.claim.assignment.musician if expense and expense.claim_id else None
    if musician is not None and musician.membership_id:
        membership_id, name = musician.membership_id, musician.name or booking.counterparty
    elif musician is not None and musician.name:
        membership_id, name = None, musician.name
    else:
        membership_id, name = booking.membership_id, booking.counterparty
    return {
        "membership_id": membership_id,
        "name": name,
        "allowance": booking.allowance,
        "order": (booking.date, booking.organization_id, booking.number),
        "row": {
            "id": booking.id,
            "source": "booking",
            "display_number": booking.display_number,
            "date": booking.date,
            "amount": booking.amount,
            "text": booking.text,
            "unit": booking.organization.name if booking.organization_id != org.pk else "",
        },
    }


def _waiver_entry(donation: Donation, org) -> dict:
    return {
        "membership_id": donation.membership_id,
        "name": donation.donor_name,
        "allowance": donation.allowance,
        "order": (donation.date, donation.pk),
        "row": {
            "id": donation.id,
            "source": "waiver",
            "display_number": gettext("Verzicht (Aufwandsspende)"),
            "date": donation.date,
            "amount": donation.amount,
            "text": donation.note,
            "unit": donation.organization.name if donation.organization_id != org.pk else "",
        },
    }


def _per_unit(org, orgs, read) -> list:
    """Liest die eigene Einheit im Kontext der Anfrage und jede Untereinheit strikt in ihrem
    eigenen Bereich (eigene RLS-Zeilen), wie ``tax._totals_of``. ``read`` lädt die Daten
    vollständig, solange der Bereich gilt."""
    rows: list = []
    for unit in orgs:
        if unit.pk == org.pk:
            rows.extend(read([unit]))
        else:
            with unit_context(unit.pk):
                rows.extend(read([unit]))
    return rows


def _memberships(org, ids: set[int]) -> dict:
    """Mitgliedschaften mit Akte, im Kontext der Anfrage gelesen. Im Arbeitsbereich einer
    Untereinheit liegen sie im Datenbereich darüber (wie ``billing.units.member_of``)."""
    from members.models import Membership
    from organizations.models import Organization

    if not ids:
        return {}
    found = {m.pk: m for m in Membership.objects.filter(pk__in=ids).select_related("person")}
    missing = ids - found.keys()
    area = org.organization_id
    if missing and org.type == Organization.Type.UNIT and area and area != org.pk:
        with tenant_context(area):
            found.update(
                (m.pk, m)
                for m in Membership.objects.filter(
                    pk__in=missing, organization_id=area
                ).select_related("person")
            )
    return found


def _person_of(entry: dict, memberships: dict) -> tuple[str, str, object]:
    """Schlüssel, Name und Mitgliedschaft der Person einer Zahlung."""
    membership_id = entry["membership_id"]
    if membership_id:
        membership = memberships.get(membership_id)
        if membership is not None:
            return (*_membership_key(membership), membership)
        # Nicht lesbar: je Mitgliedschaft getrennt zählen, nicht mit Freitext mischen
        return f"m{membership_id}", (entry["name"] or "").strip(), None
    return (*_free_text(entry["name"] or ""), None)


def _board_people(org, orgs, year: int) -> set[int]:
    """Personen (Akten) mit Vorstandsrolle irgendwann im Kalenderjahr.

    Die Rollenzuordnungen einer Untereinheit mit eigenem Arbeitsbereich sieht der Verein
    unter dem Zeilenschutz nicht; sie werden wie die Buchungen in deren Bereich gelesen."""
    from access.models import RoleAssignment

    first, last = datetime.date(year, 1, 1), datetime.date(year, 12, 31)

    def read(units):
        return list(
            RoleAssignment.objects.filter(
                organization__in=units,
                role__is_board=True,
                person__isnull=False,
                valid_from__lte=last,
            )
            .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=first))
            .values_list("person_id", flat=True)
        )

    return set(_per_unit(org, orgs, read))


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
        # Mitgliedschaft und Akte nicht mitladen: Im Bereich einer Untereinheit sind sie
        # nicht sichtbar (AZ-04); ``_memberships`` löst sie danach auf.
        .select_related("organization", "performance_expense__claim__assignment__musician")
        .order_by("date", "organization_id", "number")
    )


def waivers(orgs, year: int):
    """Aufwandsspenden aus dem Verzicht auf eine Pauschale."""
    return (
        Donation.objects.filter(organization__in=orgs, waiver=True, date__year=year)
        .exclude(allowance="")
        .select_related("organization")
        .order_by("date", "pk")
    )


def _music_amounts(orgs, year: int) -> list[Decimal]:
    """Beträge der Auszahlungen aus der Musikerabrechnung ohne gewählte Vergütungsart."""
    return list(
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


def _music_unassigned(rows: list[Decimal]) -> dict | None:
    if not rows:
        return None
    return {"count": len(rows), "total": sum(rows, Decimal("0"))}


def report(org, year: int) -> dict:
    limit = limits(year)
    orgs, root = _orgs(org)
    board = _board_people(org, orgs, year)
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

    # Erst je Einheit in ihrem Bereich lesen, dann wie bisher über alle Einheiten ordnen
    paid = sorted(
        _per_unit(org, orgs, lambda o: [_booking_entry(b, org) for b in bookings(o, year)]),
        key=lambda e: e["order"],
    )
    waived = sorted(
        _per_unit(org, orgs, lambda o: [_waiver_entry(d, org) for d in waivers(o, year)]),
        key=lambda e: e["order"],
    )
    memberships = _memberships(
        org, {e["membership_id"] for e in (*paid, *waived) if e["membership_id"]}
    )
    for entry in (*paid, *waived):
        add(*_person_of(entry, memberships), entry["allowance"], entry["row"])
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
    music = _music_unassigned(_per_unit(org, orgs, lambda o: _music_amounts(o, year)))
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
