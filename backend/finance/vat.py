"""Umsatzsteuer in der Kasse (Konzept vereinskasse-steuern, S2).

Jede Buchung kann einen Steuersatz tragen (Vorgabe aus der Kategorie). Der Betrag bleibt
brutto; Steuer und Netto werden daraus berechnet. Die Auswertung für die
Umsatzsteuer-Voranmeldung zählt je Zeitraum:

- Umsätze zu 19 % (Kennzahl 81) und 7 % (Kennzahl 86) mit Bemessungsgrundlage und Steuer,
- steuerfreie Umsätze ohne Vorsteuerabzug (Kennzahl 48),
- Vorsteuer (Kennzahl 66) aus Ausgaben außerhalb des ideellen Bereichs, bei gemischt
  genutzten Ausgaben anteilig, oder statt dessen pauschal 7 % der steuerpflichtigen Umsätze
  nach § 23a UStG (Kennzahl 63), wenn diese im Vorjahr 50.000 € nicht überstiegen haben,
- die Zahllast bzw. den Überschuss (Kennzahl 83).

Ein Storno mindert die Seite der stornierten Buchung. Untereinheiten, die steuerlich zum
Verein gehören, zählen mit; der Verein ist ein Unternehmer (§ 2 UStG). Keine Übermittlung an
ELSTER, nur Vorlage zum Übertragen.
"""

from __future__ import annotations

import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.utils.translation import gettext

from .models import Booking, TaxArea, VatRate

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
RATES = {VatRate.STANDARD: Decimal("19"), VatRate.REDUCED: Decimal("7")}
# Vorsteuer nur im unternehmerischen Bereich
INPUT_AREAS = {TaxArea.ASSETS, TaxArea.PURPOSE, TaxArea.BUSINESS}
FLAT_RATE = Decimal("7")  # § 23a Abs. 1 UStG
FLAT_LIMIT = Decimal("50000")  # § 23a Abs. 2 UStG, steuerpflichtiger Umsatz im Vorjahr
PERIODS = ("month", "quarter", "year")


def split(gross: Decimal, rate: str) -> tuple[Decimal, Decimal]:
    """(Netto, Steuer) aus einem Bruttobetrag."""
    percent = RATES.get(rate)
    if percent is None:
        return gross, ZERO
    tax = (gross * percent / (100 + percent)).quantize(CENT, rounding=ROUND_HALF_UP)
    return gross - tax, tax


def period_range(year: int, period: str, index: int) -> tuple[datetime.date, datetime.date]:
    if period == "month":
        first = datetime.date(year, index, 1)
        nxt = datetime.date(year + (index == 12), index % 12 + 1, 1)
    elif period == "quarter":
        first = datetime.date(year, 3 * index - 2, 1)
        nxt = datetime.date(year + (index == 4), (3 * index) % 12 + 1, 1)
    else:
        first, nxt = datetime.date(year, 1, 1), datetime.date(year + 1, 1, 1)
    return first, nxt - datetime.timedelta(days=1)


def period_label(year: int, period: str, index: int) -> str:
    if period == "month":
        return f"{index:02d}/{year}"
    if period == "quarter":
        return gettext("{q}. Quartal {y}").format(q=index, y=year)
    return str(year)


def period_count(period: str) -> int:
    return {"month": 12, "quarter": 4}.get(period, 1)


def _bookings(orgs, start: datetime.date, last: datetime.date):
    return (
        Booking.objects.filter(organization__in=orgs, date__gte=start, date__lte=last)
        .exclude(kind=Booking.Kind.TRANSFER)
        .select_related("category", "cancels__category")
    )


def totals(orgs, start: datetime.date, last: datetime.date) -> dict:
    """Summen eines Zeitraums; Beträge in Euro und Cent."""
    out = {
        "base_19": ZERO,
        "tax_19": ZERO,
        "base_7": ZERO,
        "tax_7": ZERO,
        "exempt": ZERO,
        "input_tax": ZERO,
        "ideal_with_vat": 0,
    }
    for b in _bookings(orgs, start, last):
        # Ein Storno zählt mit Satz, Bereich und Anteil der stornierten Buchung
        original = b.cancels if b.cancels_id else b
        rate = original.vat_rate
        if not rate:
            continue
        sign = -1 if b.cancels_id else 1
        net, tax = split(b.amount, rate)
        area = original.tax_area_value
        if original.kind == Booking.Kind.INCOME:
            if area in ("", TaxArea.IDEAL) and not b.cancels_id:
                out["ideal_with_vat"] += 1
            if rate == VatRate.EXEMPT:
                out["exempt"] += sign * b.amount
            elif rate == VatRate.STANDARD:
                out["base_19"] += sign * net
                out["tax_19"] += sign * tax
            elif rate == VatRate.REDUCED:
                out["base_7"] += sign * net
                out["tax_7"] += sign * tax
        elif area in INPUT_AREAS and rate in RATES:
            share = Decimal(original.input_tax_share) / 100
            out["input_tax"] += sign * (tax * share).quantize(CENT, rounding=ROUND_HALF_UP)
    return out


def _euros(value: Decimal) -> int:
    """Bemessungsgrundlagen trägt man in ganzen Euro ein (Cent fallen weg)."""
    return int(value)


def report(org, year: int, index: int | None = None, period: str | None = None) -> dict:
    from .tax import _vat_registered, tax_root, tax_units

    period = period if period in PERIODS else org.vat_period
    count = period_count(period)
    index = index if index and 1 <= index <= count else 1
    root = tax_root(org)
    orgs = [org, *tax_units(org)] if root.pk == org.pk else [org]
    start, last = period_range(year, period, index)
    t = totals(orgs, start, last)
    taxable = t["base_19"] + t["base_7"]
    prev = totals(orgs, datetime.date(year - 1, 1, 1), datetime.date(year - 1, 12, 31))
    prev_taxable = prev["base_19"] + prev["base_7"]
    flat_allowed = prev_taxable <= FLAT_LIMIT
    flat = org.vat_flat_rate and flat_allowed
    flat_input = (taxable * FLAT_RATE / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    input_tax = flat_input if flat else t["input_tax"]
    output_tax = t["tax_19"] + t["tax_7"]
    lines = [
        {
            "code": "81",
            "label": gettext("Steuerpflichtige Umsätze zu 19 %"),
            "base": t["base_19"],
            "base_euros": _euros(t["base_19"]),
            "tax": t["tax_19"],
        },
        {
            "code": "86",
            "label": gettext("Steuerpflichtige Umsätze zu 7 %"),
            "base": t["base_7"],
            "base_euros": _euros(t["base_7"]),
            "tax": t["tax_7"],
        },
        {
            "code": "48",
            "label": gettext("Steuerfreie Umsätze ohne Vorsteuerabzug"),
            "base": t["exempt"],
            "base_euros": _euros(t["exempt"]),
            "tax": None,
        },
        {
            "code": "63" if flat else "66",
            "label": gettext("Vorsteuer pauschal nach § 23a UStG")
            if flat
            else gettext("Vorsteuerbeträge aus Rechnungen"),
            "base": None,
            "base_euros": None,
            "tax": input_tax,
        },
        {
            "code": "83",
            "label": gettext("Verbleibende Umsatzsteuer-Vorauszahlung bzw. Überschuss (−)"),
            "base": None,
            "base_euros": None,
            "tax": output_tax - input_tax,
        },
    ]
    registered = _vat_registered(root)
    warnings = []
    if not registered:
        warnings.append(
            {
                "kind": "small",
                "text": gettext(
                    "Der Verein ist als Kleinunternehmer eingetragen (§ 19 UStG). Dann "
                    "wird keine Umsatzsteuer abgeführt und keine Vorsteuer abgezogen; die "
                    "Auswertung zeigt nur, was bei Steuerpflicht anfiele."
                ),
            }
        )
    if t["ideal_with_vat"]:
        warnings.append(
            {
                "kind": "ideal",
                "text": gettext(
                    "{n} Einnahmen im ideellen Bereich oder ohne Bereich haben einen "
                    "Steuersatz. Mitgliedsbeiträge und Spenden sind nicht steuerbar; bitte "
                    "die Buchungen prüfen."
                ).format(n=t["ideal_with_vat"]),
            }
        )
    if org.vat_flat_rate and not flat_allowed:
        warnings.append(
            {
                "kind": "flat",
                "text": gettext(
                    "Die Vorsteuerpauschale ist gewählt, aber die steuerpflichtigen Umsätze "
                    "des Vorjahres lagen über 50.000 €. Gezählt wird deshalb die "
                    "tatsächliche Vorsteuer (§ 23a Abs. 2 UStG)."
                ),
            }
        )
    return {
        "year": year,
        "period": period,
        "index": index,
        "label": period_label(year, period, index),
        "start": start,
        "end": last,
        "periods": [
            {"index": i, "label": period_label(year, period, i)} for i in range(1, count + 1)
        ],
        "registered": registered,
        "flat_rate": org.vat_flat_rate,
        "flat_rate_used": flat,
        "flat_rate_allowed": flat_allowed,
        "previous_taxable": prev_taxable,
        "actual_input_tax": t["input_tax"],
        "flat_input_tax": flat_input,
        "lines": lines,
        "units": [u.name for u in orgs[1:]],
        "counted_at": root.name if root.pk != org.pk else "",
        "warnings": warnings,
    }
