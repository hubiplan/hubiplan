"""Höchstbeträge und Vorschläge für Rücklagen (Konzept vereinskasse-steuern, S5).

Freie Rücklage (§ 62 Abs. 1 Nr. 3 AO): höchstens ein Drittel des Überschusses aus der
Vermögensverwaltung plus 10 % der übrigen zeitnah zu verwendenden Mittel eines Jahres. Das
sind die Einnahmen des ideellen Bereichs und die Überschüsse aus Zweckbetrieben und dem
wirtschaftlichen Geschäftsbetrieb (AEAO zu § 62, Nr. 9). Wird der Höchstbetrag nicht
ausgeschöpft, lässt sich der Rest in den zwei folgenden Jahren nachholen (§ 62 Abs. 1 Nr. 3
Satz 2 AO). Einnahmen ohne steuerlichen Bereich zählen wie ideelle Einnahmen.

Wiederbeschaffungsrücklage (§ 62 Abs. 1 Nr. 2 AO): Als Anhaltspunkt für die jährliche
Zuführung dient die Abschreibung laut Anlagenverzeichnis.

Alles ist ein Anhaltspunkt für den Vorstand, keine Steuerberatung.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from django.db.models import Sum

from access.modules import module_on

from .models import Reserve, ReserveMovement, TaxArea

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
# Ab diesen Jahreseinnahmen erwartet das Finanzamt in der Regel eine
# Mittelverwendungsrechnung (Konzept S5)
USE_OF_FUNDS_FROM = Decimal("100000")
CARRY_YEARS = 2


def _down(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_DOWN)


def basis(org, year: int) -> dict:
    """Bemessungsgrundlage der freien Rücklage für ein Geschäftsjahr der Einheit."""
    from .tax import area_totals

    start, last = org.fiscal_range(year)
    totals = area_totals(org.pk, start, last)

    def get(area: str, side: str) -> Decimal:
        return totals.get(area, {}).get(side, ZERO)

    def result(area: str) -> Decimal:
        return get(area, "income") - get(area, "expense")

    assets_surplus = max(result(TaxArea.ASSETS), ZERO)
    ideal_income = get(TaxArea.IDEAL, "income") + get("", "income")
    purpose_surplus = max(result(TaxArea.PURPOSE), ZERO)
    business_surplus = max(result(TaxArea.BUSINESS), ZERO)
    other = ideal_income + purpose_surplus + business_surplus
    income = sum((v["income"] for v in totals.values()), ZERO)
    return {
        "assets_surplus": assets_surplus,
        "ideal_income": ideal_income,
        "purpose_surplus": purpose_surplus,
        "business_surplus": business_surplus,
        "other_funds": other,
        "limit": _down(assets_surplus / 3) + _down(other / 10),
        "income": income,
    }


def _free_added(org) -> dict[int, Decimal]:
    rows = (
        ReserveMovement.objects.filter(
            organization=org,
            reserve__kind=Reserve.Kind.FREE,
            direction=ReserveMovement.Direction.ADD,
        )
        .values("year")
        .annotate(s=Sum("amount"))
        .order_by()
    )
    return {row["year"]: row["s"] or ZERO for row in rows}


def free_reserve(org, year: int) -> dict:
    """Höchstbetrag der freien Rücklage für ``year`` mit Nachholung aus zwei Vorjahren.

    Zuführungen verbrauchen zuerst den ältesten noch nachholbaren Rest."""
    added = _free_added(org)
    first = year - 2 * CARRY_YEARS
    pool: list[list] = []  # [Jahr, noch offen]
    limits: dict[int, Decimal] = {}
    carry = ZERO
    for y in range(first, year + 1):
        limits[y] = basis(org, y)["limit"]
        pool = [p for p in pool if y - p[0] <= CARRY_YEARS]
        if y == year:
            carry = sum((p[1] for p in pool), ZERO)
        pool.append([y, limits[y]])
        rest = added.get(y, ZERO)
        for entry in pool:
            take = min(entry[1], rest)
            entry[1] -= take
            rest -= take
    current = basis(org, year)
    available = current["limit"] + carry
    used = added.get(year, ZERO)
    return {
        **current,
        "carry": carry,
        "available": available,
        "added": used,
        "over": max(used - available, ZERO),
    }


def replacement_hint(org, year: int) -> dict | None:
    """Abschreibung des Jahres als Anhaltspunkt für die Wiederbeschaffungsrücklage."""
    if not module_on(org, "tax"):
        return None
    from . import assets

    register = assets.register(org, year)
    depreciation = register["totals"]["depreciation"]
    if not depreciation:
        return None
    added = (
        ReserveMovement.objects.filter(
            organization=org,
            reserve__kind=Reserve.Kind.REPLACEMENT,
            direction=ReserveMovement.Direction.ADD,
            year=year,
        ).aggregate(s=Sum("amount"))["s"]
        or ZERO
    )
    return {"depreciation": depreciation, "added": added}


def report(org, year: int) -> dict:
    free = free_reserve(org, year)
    return {
        "year": year,
        "label": org.fiscal_label(year),
        "free": free,
        "replacement": replacement_hint(org, year),
        "use_of_funds": free["income"] >= USE_OF_FUNDS_FROM,
        "use_of_funds_from": USE_OF_FUNDS_FROM,
    }
