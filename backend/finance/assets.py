"""Anlagenverzeichnis und Abschreibung (AfA), Konzept vereinskasse-steuern, Abschnitt 5.

Die AfA erscheint nur in der steuerlichen Auswertung. Dort ersetzt sie für die
Ergebnisrechnung die Ausgabe der Anschaffung: Die Ausgabe wird im Jahr der Zahlung
zurückgerechnet, die AfA über die Jahre abgezogen. Methoden:

- linear: monatsgenau über die Nutzungsdauer, ab dem Monat der Anschaffung (§ 7 Abs. 1 EStG)
- gwg: geringwertig, voll im Jahr der Anschaffung (§ 6 Abs. 2 EStG)
- pool: Sammelposten, je ein Fünftel in fünf Geschäftsjahren, Abgang ändert nichts
  (§ 6 Abs. 2a EStG)
- none: nur Verzeichnis; die Ausgabe bleibt, wie sie gebucht ist
"""

from __future__ import annotations

import datetime
from decimal import ROUND_HALF_UP, Decimal

from .models import FixedAsset, TaxArea

ZERO = Decimal("0")
CENT = Decimal("0.01")
SUGGEST_FROM = Decimal("250")
M = FixedAsset.Method


def _round(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _month_index(day: datetime.date) -> int:
    return day.year * 12 + day.month - 1


def accumulated(asset: FixedAsset, org, day: datetime.date) -> Decimal:
    """Abschreibung von der Anschaffung bis einschließlich ``day`` (ohne Restwert beim Abgang)."""
    if day < asset.acquired_on or asset.method == M.NONE:
        return ZERO
    if asset.method == M.GWG:
        return asset.cost
    if asset.method == M.POOL:
        first = org.fiscal_year_of(asset.acquired_on)
        years = min(max(org.fiscal_year_of(day) - first + 1, 0), 5)
        return _round(asset.cost * years / 5)
    total = asset.useful_life * 12
    end = day
    if asset.disposed_on and asset.disposed_on < end:
        end = asset.disposed_on
    months = min(max(_month_index(end) - _month_index(asset.acquired_on) + 1, 0), total)
    return _round(asset.cost * months / total)


def year_values(asset: FixedAsset, org, year: int) -> dict:
    """Werte eines Geschäftsjahres: AfA, Restwert beim Abgang, Buchwert am Anfang und Ende."""
    start, last = org.fiscal_range(year)
    before = start - datetime.timedelta(days=1)
    gone_before = asset.disposed_on is not None and asset.disposed_on < start
    gone_now = asset.disposed_on is not None and start <= asset.disposed_on <= last
    depreciation = accumulated(asset, org, last) - accumulated(asset, org, before)
    if asset.method == M.NONE:
        book_start = asset.cost if asset.acquired_on < start and not gone_before else ZERO
        book_end = (
            asset.cost if asset.acquired_on <= last and not (gone_before or gone_now) else ZERO
        )
        residual = ZERO
    else:
        book_start = ZERO
        if asset.acquired_on < start and not (gone_before and asset.method != M.POOL):
            book_start = asset.cost - accumulated(asset, org, before)
        book_end = ZERO
        if asset.acquired_on <= last and not ((gone_before or gone_now) and asset.method != M.POOL):
            book_end = asset.cost - accumulated(asset, org, last)
        residual = ZERO
        if gone_now and asset.method == M.LINEAR:
            residual = asset.cost - accumulated(asset, org, asset.disposed_on)
    return {
        "depreciation": depreciation,
        "residual": residual,
        "book_start": book_start,
        "book_end": book_end,
    }


def register(org, year: int) -> dict:
    """Anlagenverzeichnis mit den Werten eines Geschäftsjahres."""
    start, last = org.fiscal_range(year)
    rows = []
    totals = {"depreciation": ZERO, "residual": ZERO, "book_end": ZERO}
    qs = (
        FixedAsset.objects.filter(organization=org)
        .select_related("booking__organization", "material_item")
        .order_by("acquired_on", "name", "pk")
    )
    for asset in qs:
        values = year_values(asset, org, year)
        for key in totals:
            totals[key] += values[key]
        rows.append({"asset": asset, **values})
    return {
        "year": year,
        "label": org.fiscal_label(year),
        "start_date": start,
        "end_date": last,
        "rows": rows,
        "totals": totals,
    }


def tax_adjustment(org, start: datetime.date, last: datetime.date) -> dict | None:
    """Korrektur der Ergebnisse je Bereich für die steuerliche Auswertung.

    Anschaffungsausgaben im Zeitraum werden zurückgerechnet, die AfA und der Restwert
    abgegangener Anlagen abgezogen. ``None``, wenn es keine abzuschreibenden Anlagen gibt."""
    year = org.fiscal_year_of(start)
    assets = list(
        FixedAsset.objects.filter(organization=org).exclude(method=M.NONE).select_related("booking")
    )
    if not assets:
        return None
    areas: dict[str, dict] = {}
    for asset in assets:
        values = year_values(asset, org, year)
        purchase = ZERO
        if asset.booking_id and start <= asset.booking.date <= last:
            purchase = asset.cost
        if not (purchase or values["depreciation"] or values["residual"]):
            continue
        entry = areas.setdefault(
            asset.tax_area,
            {
                "area": asset.tax_area,
                "label": str(TaxArea(asset.tax_area).label),
                "purchases": ZERO,
                "depreciation": ZERO,
                "residual": ZERO,
            },
        )
        entry["purchases"] += purchase
        entry["depreciation"] += values["depreciation"]
        entry["residual"] += values["residual"]
    order = [a.value for a in TaxArea]
    rows = sorted(areas.values(), key=lambda e: order.index(e["area"]))
    for row in rows:
        row["adjustment"] = row["purchases"] - row["depreciation"] - row["residual"]
    business = next((r["adjustment"] for r in rows if r["area"] == TaxArea.BUSINESS), ZERO)
    return {"areas": rows, "business_adjustment": business}
