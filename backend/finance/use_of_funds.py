"""Mittelverwendungsrechnung (Konzept vereinskasse-steuern, S5).

Gemeinnützige Mittel sind zeitnah zu verwenden: spätestens bis zum Ende des zweiten
Kalender- bzw. Wirtschaftsjahres nach dem Zufluss (§ 55 Abs. 1 Nr. 5 AO). Ab 100.000 €
Jahreseinnahmen erwartet das Finanzamt in der Regel einen Nachweis. Die Rechnung hier ist ein
vereinfachter Anhaltspunkt aus dem Kassenbuch:

- zugeflossen: Einnahmen des ideellen Bereichs (und ohne Bereich) sowie die Überschüsse aus
  Vermögensverwaltung, Zweckbetrieben und wirtschaftlichem Geschäftsbetrieb,
- satzungsgemäß verwendet: Ausgaben des ideellen Bereichs (und ohne Bereich) sowie Verluste
  der Zweckbetriebe,
- Rücklagen: Zuführungen binden Mittel, Auflösungen geben sie wieder frei,
- Verwendung zuerst aus den ältesten Mitteln (Vortrag nach Jahr der Herkunft).
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum

from .models import ReserveMovement, TaxArea

ZERO = Decimal("0.00")
DEADLINE_YEARS = 2
HISTORY_YEARS = 5


def _year_values(org, year: int) -> dict:
    from .tax import area_totals

    start, last = org.fiscal_range(year)
    totals = area_totals(org.pk, start, last)

    def get(area: str, side: str) -> Decimal:
        return totals.get(area, {}).get(side, ZERO)

    def result(area: str) -> Decimal:
        return get(area, "income") - get(area, "expense")

    purpose = result(TaxArea.PURPOSE)
    inflow = (
        get(TaxArea.IDEAL, "income")
        + get("", "income")
        + max(result(TaxArea.ASSETS), ZERO)
        + max(purpose, ZERO)
        + max(result(TaxArea.BUSINESS), ZERO)
    )
    used = get(TaxArea.IDEAL, "expense") + get("", "expense") + max(-purpose, ZERO)
    moves = {
        row["direction"]: row["s"] or ZERO
        for row in ReserveMovement.objects.filter(organization=org, year=year)
        .values("direction")
        .annotate(s=Sum("amount"))
        .order_by()
    }
    return {
        "inflow": inflow,
        "used": used,
        "reserve_add": moves.get(ReserveMovement.Direction.ADD, ZERO),
        "reserve_release": moves.get(ReserveMovement.Direction.RELEASE, ZERO),
    }


def report(org, year: int) -> dict:
    pool: list[list] = []  # [Herkunftsjahr, noch nicht verwendet]
    rows = []
    for y in range(year - HISTORY_YEARS, year + 1):
        values = _year_values(org, y)
        carry_in = sum((p[1] for p in pool), ZERO)
        pool.append([y, values["inflow"] + values["reserve_release"]])
        need = values["used"] + values["reserve_add"]
        for entry in pool:
            take = min(entry[1], need)
            entry[1] -= take
            need -= take
        # Mehr verwendet als vorhanden (etwa aus Vermögen vor dem Betrachtungszeitraum)
        uncovered = need
        pool = [p for p in pool if p[1] > 0]
        carry_out = sum((p[1] for p in pool), ZERO)
        rows.append(
            {
                "year": y,
                "label": org.fiscal_label(y),
                "carry_in": carry_in,
                **values,
                "uncovered": uncovered,
                "carry_out": carry_out,
            }
        )
    current = rows[-1]
    by_origin = [
        {
            "year": origin,
            "label": org.fiscal_label(origin),
            "amount": amount,
            "deadline": org.fiscal_label(origin + DEADLINE_YEARS),
            # Frist schon abgelaufen bzw. endet mit diesem Geschäftsjahr
            "overdue": origin + DEADLINE_YEARS < year,
            "due_now": origin + DEADLINE_YEARS == year,
        }
        for origin, amount in pool
    ]
    return {
        "year": year,
        "label": org.fiscal_label(year),
        "current": current,
        "years": rows[-3:],
        "by_origin": by_origin,
        "overdue": sum((o["amount"] for o in by_origin if o["overdue"]), ZERO),
        "due_now": sum((o["amount"] for o in by_origin if o["due_now"]), ZERO),
    }
