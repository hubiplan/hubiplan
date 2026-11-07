"""Steuerliche Auswertung eines Geschäftsjahres (Konzept vereinskasse-steuern, Paket S1).

Rechnet aus den Buchungen, was das Finanzamt bei einer steuerbegünstigten Körperschaft
wissen will:

- Einnahmen und Ausgaben je steuerlichem Bereich (Stornos mit der stornierten Buchung
  verrechnet),
- die Freigrenze des wirtschaftlichen Geschäftsbetriebs (§ 64 Abs. 3 AO) als Ampel,
- Verluste im wirtschaftlichen Geschäftsbetrieb (§ 55 Abs. 1 Nr. 1 AO),
- einen Anhaltspunkt für die Kleinunternehmergrenze (§ 19 UStG),
- einen Hinweis, wann die nächste Steuererklärung fällig ist.

Steuerlich ist der Verein ein Ganzes: Untereinheiten mit eigener Kasse zählen beim Verein
mit (§ 64 Abs. 4 AO verbietet, einen Verein in Abteilungen aufzuteilen), außer sie sind als
„steuerlich selbständig“ markiert. Die Beträge der Untereinheiten liest die Auswertung
jeweils im Bereich der Untereinheit (RLS), übernommen werden nur Summen.
"""

from __future__ import annotations

import datetime
import re
from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext

from core.tenancy import unit_context
from organizations.models import Organization

from .models import Booking, DonationSettings, TaxArea

ZERO = Decimal("0.00")
WARN_SHARE = Decimal("0.8")

# Freigrenze für Einnahmen einschließlich Umsatzsteuer aus wirtschaftlichen
# Geschäftsbetrieben (§ 64 Abs. 3 AO), je Veranlagungszeitraum ab dem genannten Jahr
FREE_LIMITS = (
    (2026, Decimal("50000")),  # Steueränderungsgesetz 2025
    (2020, Decimal("45000")),  # Jahressteuergesetz 2020
    (2007, Decimal("35000")),
)
# Kleinunternehmer (§ 19 UStG): Umsatz im Vorjahr und im laufenden Jahr
SMALL_LIMITS = (
    (2025, Decimal("25000"), Decimal("100000")),  # Jahressteuergesetz 2024, harte Grenze
    (2020, Decimal("22000"), Decimal("50000")),  # laufendes Jahr: Prognose
)
# Bereiche, deren Einnahmen als Umsatz zählen (Anhaltspunkt, ohne Steuersatz je Buchung)
TURNOVER_AREAS = (TaxArea.PURPOSE, TaxArea.BUSINESS)
# Eine Körperschaft wird regelmäßig für drei Jahre geprüft (AEAO zu § 59, Nr. 7)
DECLARATION_YEARS = 3


def free_limit(year: int) -> Decimal:
    for since, limit in FREE_LIMITS:
        if year >= since:
            return limit
    return FREE_LIMITS[-1][1]


def small_limits(year: int) -> tuple[Decimal, Decimal]:
    for since, previous, current in SMALL_LIMITS:
        if year >= since:
            return previous, current
    return SMALL_LIMITS[-1][1], SMALL_LIMITS[-1][2]


def tax_root(org: Organization) -> Organization:
    """Die Einheit, bei der das Finanzamt die Zahlen zusammenrechnet.

    Eine Untereinheit gehört zur Einheit darüber, bis eine als steuerlich selbständig
    markiert ist; Vereine und Dachverbände sind immer eigene Steuersubjekte."""
    node = org
    while node.type == Organization.Type.UNIT and not node.tax_independent and node.parent_id:
        node = node.parent
    return node


def tax_units(root: Organization) -> list[Organization]:
    """Untereinheiten mit eigener Kasse, deren Zahlen bei ``root`` mitzählen."""
    area = root.organization_id if root.type == Organization.Type.UNIT else root.pk
    candidates = Organization.objects.filter(
        type=Organization.Type.UNIT, own_workspace=True, organization_id=area
    ).select_related("parent")
    return [
        u
        for u in candidates.order_by("sort_order", "name")
        if u.pk != root.pk and "finance" in (u.enabled_modules or []) and tax_root(u).pk == root.pk
    ]


def area_totals(org_id: int, start: datetime.date, last: datetime.date) -> dict[str, dict]:
    """Einnahmen und Ausgaben je Bereich; ein Storno mindert die Art der stornierten
    Buchung, statt als Gegenbuchung die andere Seite aufzublähen."""
    rows = (
        Booking.objects.filter(organization_id=org_id, date__gte=start, date__lte=last)
        .exclude(kind=Booking.Kind.TRANSFER)
        .values("kind", "frozen", "frozen_tax_area", "category__tax_area", "cancels__kind")
        .annotate(total=Sum("amount"))
        .order_by()
    )
    totals: dict[str, dict] = defaultdict(lambda: {"income": ZERO, "expense": ZERO})
    for row in rows:
        area = (row["frozen_tax_area"] if row["frozen"] else row["category__tax_area"]) or ""
        original = row["cancels__kind"]
        if original is None:
            side = "income" if row["kind"] == Booking.Kind.INCOME else "expense"
            totals[area][side] += row["total"]
        else:
            side = "income" if original == Booking.Kind.INCOME else "expense"
            totals[area][side] -= row["total"]
    return totals


def _totals_of(org: Organization, start, last, *, foreign: bool = False) -> dict[str, dict]:
    if foreign:
        # Strikt im Bereich der Untereinheit lesen (eigene RLS-Zeilen)
        with unit_context(org.pk):
            return area_totals(org.pk, start, last)
    return area_totals(org.pk, start, last)


def _area_list(totals: dict[str, dict]) -> list[dict]:
    labels = dict(TaxArea.choices)
    result = []
    for key in [*TaxArea.values, ""]:
        if key in totals:
            income, expense = totals[key]["income"], totals[key]["expense"]
            if not income and not expense:
                continue
            result.append(
                {
                    "area": key,
                    "label": str(labels[key]) if key else gettext("ohne Zuordnung"),
                    "income": income,
                    "expense": expense,
                    "result": income - expense,
                }
            )
    return result


def _merge(target: dict[str, dict], source: dict[str, dict]) -> None:
    for area, values in source.items():
        entry = target.setdefault(area, {"income": ZERO, "expense": ZERO})
        entry["income"] += values["income"]
        entry["expense"] += values["expense"]


def _entity_totals(root: Organization, units: list[Organization], start, last):
    combined: dict[str, dict] = {}
    parts = []
    for org in [root, *units]:
        totals = _totals_of(org, start, last, foreign=org.pk != root.pk)
        _merge(combined, totals)
        parts.append((org, totals))
    return combined, parts


def _get(totals: dict[str, dict], area: str, side: str) -> Decimal:
    return totals.get(area, {}).get(side, ZERO)


def _turnover(totals: dict[str, dict]) -> Decimal:
    return sum((_get(totals, a, "income") for a in TURNOVER_AREAS), ZERO)


def _status(value: Decimal, limit: Decimal) -> str:
    if value > limit:
        return "over"
    if value >= limit * WARN_SHARE:
        return "warn"
    return "ok"


def _vat_registered(org: Organization) -> bool:
    """Weist die Einheit Umsatzsteuer aus, ist sie kein Kleinunternehmer."""
    from billing.models import BillingSettings

    cfg = BillingSettings.objects.filter(organization=org).only("vat_enabled").first()
    return bool(cfg and cfg.vat_enabled)


def declaration_hint(org: Organization, today: datetime.date | None = None) -> dict | None:
    """Wann die nächste Steuererklärung (Gemeinnützigkeitsprüfung) ansteht.

    Grundlage ist der letzte geprüfte Zeitraum aus den Angaben zum Freistellungsbescheid;
    das Finanzamt prüft in der Regel alle drei Jahre."""
    today = today or timezone.localdate()
    cfg = DonationSettings.objects.filter(organization=org, enabled=True).first()
    if cfg is None:
        return None
    years = [int(y) for y in re.findall(r"(?<!\d)(\d{4})(?!\d)", cfg.assessment_period)]
    if cfg.notice != DonationSettings.Notice.EXEMPTION or not years:
        return {
            "known": False,
            "text": gettext(
                "Für die Erinnerung an die Steuererklärung fehlt der letzte geprüfte Zeitraum "
                "(Einstellungen der Zuwendungsbestätigungen)."
            ),
        }
    last = max(years)
    first_open, last_open = last + 1, last + DECLARATION_YEARS
    due = today.year > last_open
    return {
        "known": True,
        "checked_until": last,
        "next_from": first_open,
        "next_to": last_open,
        "due": due,
        "text": (
            gettext(
                "Die Jahre {a} bis {b} sind noch nicht vom Finanzamt geprüft. Die "
                "Steuererklärung dafür ist fällig, sobald das Finanzamt dazu auffordert, "
                "spätestens im Jahr {c} (Erklärung samt Anlage Gem)."
            )
            if not due
            else gettext(
                "Die Jahre {a} bis {b} sind abgelaufen und noch nicht geprüft. Bitte die "
                "Steuererklärung (samt Anlage Gem) abgeben und danach den neuen Bescheid in "
                "den Einstellungen der Zuwendungsbestätigungen eintragen."
            )
        ).format(a=first_open, b=last_open, c=last_open + 1),
    }


def report(org: Organization, year: int, today: datetime.date | None = None) -> dict:
    """Steuerliche Auswertung für ein Geschäftsjahr der Einheit ``org``."""
    today = today or timezone.localdate()
    root = tax_root(org)
    is_root = root.pk == org.pk
    # Nur die Einheit, bei der zusammengerechnet wird, sieht die Summen der Untereinheiten.
    # Eine Untereinheit sieht ihre eigenen Zahlen und den Hinweis, wo sie mitzählen.
    units = tax_units(org) if is_root else []
    start, last = org.fiscal_range(year)
    # Veranlagungszeitraum: das Kalenderjahr, in dem das Wirtschaftsjahr endet
    period = last.year

    combined, parts = _entity_totals(org, units, start, last)
    own = parts[0][1]

    business_income = _get(combined, TaxArea.BUSINESS, "income")
    business_result = business_income - _get(combined, TaxArea.BUSINESS, "expense")
    limit = free_limit(period)
    # Anlagen der eigenen Kasse: Anschaffung zurückrechnen, AfA abziehen (nur hier, nie im
    # Kassenbuch)
    from .assets import tax_adjustment

    depreciation = tax_adjustment(org, start, last)
    business_after = business_result + (
        depreciation["business_adjustment"] if depreciation else ZERO
    )

    # Ergebnis des wirtschaftlichen Geschäftsbetriebs in den beiden Vorjahren
    history = []
    for earlier in (year - 2, year - 1):
        s, e = org.fiscal_range(earlier)
        totals, _ = _entity_totals(org, units, s, e)
        history.append(
            {
                "year": earlier,
                "label": org.fiscal_label(earlier),
                "income": _get(totals, TaxArea.BUSINESS, "income"),
                "result": _get(totals, TaxArea.BUSINESS, "income")
                - _get(totals, TaxArea.BUSINESS, "expense"),
            }
        )
    warnings = []
    if business_after < 0:
        earlier_gains = sum((max(h["result"], ZERO) for h in history), ZERO)
        warnings.append(
            {
                "kind": "loss",
                "text": gettext(
                    "Der wirtschaftliche Geschäftsbetrieb hat einen Verlust von {x} €. "
                    "Verluste dürfen nicht aus Mitgliedsbeiträgen, Spenden oder anderen "
                    "Mitteln des ideellen Bereichs ausgeglichen werden (§ 55 Abs. 1 Nr. 1 "
                    "AO). Zulässig ist ein Ausgleich aus Gewinnen dieses Bereichs in den "
                    "sechs Vorjahren; in den beiden Vorjahren waren es {y} €."
                ).format(x=_euro(-business_after), y=_euro(earlier_gains)),
            }
        )
    unassigned = _get(combined, "", "income") + _get(combined, "", "expense")
    if unassigned:
        warnings.append(
            {
                "kind": "unassigned",
                "text": gettext(
                    "Buchungen über {x} € haben keinen steuerlichen Bereich. Bitte den "
                    "Kategorien einen Bereich zuordnen, sonst fehlen sie in der Ampel."
                ).format(x=_euro(unassigned)),
            }
        )

    small = None
    if is_root and not _vat_registered(org):
        previous_limit, current_limit = small_limits(period)
        prev_start, prev_last = org.fiscal_range(year - 1)
        prev_totals, _ = _entity_totals(org, units, prev_start, prev_last)
        current, previous = _turnover(combined), _turnover(prev_totals)
        status = "ok"
        if current > current_limit or previous > previous_limit:
            status = "over"
        elif current > previous_limit or current >= current_limit * WARN_SHARE:
            status = "warn"
        small = {
            "previous": previous,
            "previous_limit": previous_limit,
            "current": current,
            "current_limit": current_limit,
            "status": status,
        }

    return {
        "year": year,
        "label": org.fiscal_label(year),
        "start_date": start,
        "end_date": last,
        "period": period,
        "enabled": org.tax_areas_on,
        "root": {"id": root.pk, "name": root.name, "is_self": is_root},
        "units": [
            {
                "id": unit.pk,
                "name": unit.name,
                "tax_areas_enabled": unit.tax_areas_on,
                "business_income": _get(totals, TaxArea.BUSINESS, "income"),
                "turnover": _turnover(totals),
            }
            for unit, totals in parts[1:]
        ],
        "own_areas": _area_list(own),
        "areas": _area_list(combined),
        "free_limit": {
            "limit": limit,
            "income": business_income,
            "status": _status(business_income, limit),
            "percent": int(business_income * 100 / limit) if limit else 0,
        },
        "business_result": business_result,
        # Nach Abschreibung (None ohne abzuschreibende Anlagen)
        "depreciation": depreciation,
        "business_result_after": business_after if depreciation else None,
        "history": history,
        "small_business": small,
        "warnings": warnings,
        "declaration": declaration_hint(org, today) if is_root else None,
        "today": today,
    }


def _euro(value: Decimal) -> str:
    text = f"{value:,.2f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")
