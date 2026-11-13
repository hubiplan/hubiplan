"""Haushaltsplan: Plan und Ist je Kategorie (und Untereinheit) für ein Geschäftsjahr.

Ist sind die Einnahmen und Ausgaben des Kassenbuchs im Geschäftsjahr, ohne Umbuchungen.
Eine Stornobuchung mindert die Seite der stornierten Buchung, damit sich beides aufhebt.

Zuordnung: Eine Zeile mit Untereinheit zählt nur deren Buchungen. Eine Zeile ohne
Untereinheit zählt alle übrigen Buchungen der Kategorie. Was keiner Zeile zugeordnet ist,
steht unter „nicht geplant“.

Hochrechnung (nur im laufenden Jahr): Ist bis heute plus das, was im Vorjahr ab demselben
Tag noch dazukam. Ohne Vorjahreswerte gilt der Plan, solange das Ist ihn nicht übersteigt.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext

from .models import Booking, Budget, BudgetLine, Category

ZERO = Decimal("0.00")
MAX_LINES = 500
MAX_AMOUNT = Decimal("9999999999.99")
KINDS = (BudgetLine.Kind.INCOME, BudgetLine.Kind.EXPENSE)

Key = tuple[int, str, int | None]  # Kategorie, Art, Untereinheit


def _today() -> datetime.date:
    return timezone.localdate()


class BudgetError(Exception):
    """Fehler beim Speichern, mit Meldung je Feld bzw. Zeile."""

    def __init__(self, errors: dict):
        super().__init__(str(errors))
        self.errors = errors


def actuals(org, start: datetime.date, end: datetime.date) -> dict[Key, Decimal]:
    """Summen je Kategorie, Art und Untereinheit für start ≤ Datum < end."""
    rows = (
        Booking.objects.filter(
            organization=org, date__gte=start, date__lt=end, category__isnull=False
        )
        .exclude(kind=Booking.Kind.TRANSFER)
        .values("category_id", "department_id", "kind", "cancels__kind")
        .annotate(total=Sum("amount"))
        .order_by()
    )
    result: dict[Key, Decimal] = defaultdict(lambda: ZERO)
    for row in rows:
        original = row["cancels__kind"]
        if original:
            # Storno: zählt gegen die Seite der stornierten Buchung
            if original == Booking.Kind.TRANSFER:
                continue
            result[(row["category_id"], original, row["department_id"])] -= row["total"]
        else:
            result[(row["category_id"], row["kind"], row["department_id"])] += row["total"]
    return dict(result)


def allocate(lines: list[BudgetLine], sums: dict[Key, Decimal]):
    """Verteilt die Summen auf die Zeilen. Liefert (je Zeile, nicht geplant)."""
    own = {(ln.category_id, ln.kind, ln.department_id) for ln in lines}
    general = {(ln.category_id, ln.kind) for ln in lines if ln.department_id is None}
    per_line: dict[Key, Decimal] = defaultdict(lambda: ZERO)
    unplanned: dict[Key, Decimal] = defaultdict(lambda: ZERO)
    for (cat, kind, dept), value in sums.items():
        if (cat, kind, dept) in own:
            per_line[(cat, kind, dept)] += value
        elif (cat, kind) in general:
            per_line[(cat, kind, None)] += value
        else:
            unplanned[(cat, kind, dept)] += value
    return per_line, {k: v for k, v in unplanned.items() if v}


def _same_day_last_year(start: datetime.date, prev_start: datetime.date, day: datetime.date):
    return prev_start + (day - start)


def _years(org, year: int) -> list[dict]:
    from . import services

    today_year = org.fiscal_year_of(_today())
    found = set(services.years(org))
    found |= set(Budget.objects.filter(organization=org).values_list("year", flat=True))
    found |= {today_year, today_year + 1, year}
    return [{"year": y, "label": org.fiscal_label(y)} for y in sorted(found, reverse=True)]


def _phase(org, year: int) -> str:
    current = org.fiscal_year_of(_today())
    if year < current:
        return "past"
    if year > current:
        return "future"
    return "current"


def report(org, year: int) -> dict:
    from organizations.models import Department

    start, last = org.fiscal_range(year)
    end = last + datetime.timedelta(days=1)
    prev_start, prev_last = org.fiscal_range(year - 1)
    prev_end = prev_last + datetime.timedelta(days=1)
    phase = _phase(org, year)
    today = _today()

    budget = Budget.objects.filter(organization=org, year=year).first()
    previous = Budget.objects.filter(organization=org, year=year - 1).first()
    lines = list(budget.lines.select_related("category")) if budget else []
    prev_lines = list(previous.lines.all()) if previous else []

    now = actuals(org, start, end) if phase != "future" else {}
    before = actuals(org, prev_start, prev_end)
    per_line, unplanned = allocate(lines, now)
    prev_per_line, _rest = allocate(lines, before)
    prev_plan = {(ln.category_id, ln.kind, ln.department_id): ln.amount for ln in prev_lines}

    # Hochrechnung: was im Vorjahr ab demselben Tag noch hinzukam
    later: dict[Key, Decimal] = {}
    elapsed = None
    if phase == "current":
        cut = _same_day_last_year(start, prev_start, today) + datetime.timedelta(days=1)
        later_sums = actuals(org, max(cut, prev_start), prev_end)
        later, _rest = allocate(lines, later_sums)
        total_days = (end - start).days or 1
        elapsed = round(100 * ((today - start).days + 1) / total_days)

    cats = {c.pk: c for c in Category.objects.filter(organization=org)}
    depts = {d.pk: d for d in Department.objects.filter(organization=org)}

    def dept_name(pk):
        return depts[pk].display_name if pk in depts else None

    totals = {
        kind: {
            "plan": ZERO,
            "actual": ZERO,
            "forecast": ZERO,
            "previous_plan": ZERO,
            "previous_actual": ZERO,
        }
        for kind in KINDS
    }
    out_lines = []
    for ln in lines:
        key = (ln.category_id, ln.kind, ln.department_id)
        actual = per_line.get(key, ZERO)
        if phase == "current":
            prior = later.get(key, ZERO)
            forecast = actual + prior if prev_per_line.get(key) else max(actual, ln.amount)
        elif phase == "past":
            forecast = actual
        else:
            forecast = None
        row = {
            "id": ln.pk,
            "kind": ln.kind,
            "category": ln.category_id,
            "category_name": ln.category.name,
            "category_active": ln.category.is_active,
            "department": ln.department_id,
            "department_name": dept_name(ln.department_id),
            "amount": ln.amount,
            "note": ln.note,
            "actual": actual if phase != "future" else None,
            "forecast": forecast,
            "previous_plan": prev_plan.get(key),
            "previous_actual": prev_per_line.get(key, ZERO),
        }
        out_lines.append(row)
        t = totals[ln.kind]
        t["plan"] += ln.amount
        t["actual"] += actual
        t["forecast"] += forecast if forecast is not None else ln.amount
        t["previous_plan"] += row["previous_plan"] or ZERO
        t["previous_actual"] += row["previous_actual"]

    out_unplanned = []
    for (cat, kind, dept), value in sorted(
        unplanned.items(), key=lambda kv: (kv[0][1], cats[kv[0][0]].name.lower())
    ):
        out_unplanned.append(
            {
                "kind": kind,
                "category": cat,
                "category_name": cats[cat].name,
                "department": dept,
                "department_name": dept_name(dept),
                "actual": value,
            }
        )
        totals[kind]["actual"] += value
        if phase != "future":
            totals[kind]["forecast"] += value

    inc, exp = totals[BudgetLine.Kind.INCOME], totals[BudgetLine.Kind.EXPENSE]
    result = {k: inc[k] - exp[k] for k in inc}
    if phase == "future":
        for t in (inc, exp, result):
            t["actual"] = None
            t["forecast"] = None

    return {
        "year": year,
        "label": org.fiscal_label(year),
        "start_date": start,
        "end_date": last,
        "phase": phase,
        "elapsed_percent": elapsed,
        "years": _years(org, year),
        "previous_label": org.fiscal_label(year - 1),
        "previous_has_budget": previous is not None,
        "budget": (
            {
                "id": budget.pk,
                "status": budget.status,
                "status_label": budget.get_status_display(),
                "adopted_on": budget.adopted_on,
                "adopted_by": budget.adopted_by,
                "note": budget.note,
                "version": budget.version,
                "updated_at": budget.updated_at,
            }
            if budget
            else None
        ),
        "lines": out_lines,
        "unplanned": out_unplanned,
        "totals": {"income": inc, "expense": exp, "result": result},
    }


# --- Speichern ------------------------------------------------------------------------------


def _amount(value) -> Decimal:
    try:
        amount = Decimal(str(value).replace(",", ".")).quantize(Decimal("0.01"), ROUND_HALF_UP)
    except Exception as exc:
        raise ValueError from exc
    if not amount.is_finite() or amount < 0 or amount > MAX_AMOUNT:
        raise ValueError
    return amount


def _clean_lines(org, raw) -> list[dict]:
    from organizations.models import Department

    if not isinstance(raw, list):
        raise BudgetError({"lines": gettext("Bitte die Zeilen als Liste senden.")})
    if len(raw) > MAX_LINES:
        raise BudgetError(
            {"lines": gettext("Höchstens {n} Zeilen je Haushaltsplan.").format(n=MAX_LINES)}
        )
    cats = {c.pk: c for c in Category.objects.filter(organization=org)}
    depts = set(Department.objects.filter(organization=org).values_list("pk", flat=True))
    seen: set = set()
    clean = []
    errors: dict[int, str] = {}
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            errors[i] = gettext("Ungültige Zeile.")
            continue
        kind = item.get("kind")
        cat = item.get("category")
        dept = item.get("department") or None
        if kind not in KINDS:
            errors[i] = gettext("Bitte Einnahmen oder Ausgaben wählen.")
            continue
        if not isinstance(cat, int) or cat not in cats:
            errors[i] = gettext("Bitte eine Kategorie wählen.")
            continue
        if not cats[cat].allows(kind):
            errors[i] = gettext("Die Kategorie „{name}“ passt nicht zu {kind}.").format(
                name=cats[cat].name, kind=BudgetLine.Kind(kind).label
            )
            continue
        if dept is not None and (not isinstance(dept, int) or dept not in depts):
            errors[i] = gettext("Unbekannte Untereinheit.")
            continue
        try:
            amount = _amount(item.get("amount", ""))
        except ValueError:
            errors[i] = gettext("Bitte einen Betrag von 0 oder mehr eingeben.")
            continue
        if (kind, cat, dept) in seen:
            errors[i] = gettext("Diese Kategorie steht schon im Plan.")
            continue
        seen.add((kind, cat, dept))
        note = str(item.get("note") or "").strip()[:200]
        clean.append(
            {
                "kind": kind,
                "category_id": cat,
                "department_id": dept,
                "amount": amount,
                "note": note,
            }
        )
    if errors:
        raise BudgetError({"lines": {str(k): v for k, v in errors.items()}})
    return clean


def _locked(org, year: int) -> Budget | None:
    return Budget.objects.select_for_update().filter(organization=org, year=year).first()


def _check_version(budget: Budget | None, version) -> None:
    if budget is not None and version is not None and version != budget.version:
        raise BudgetError(
            {"version": gettext("Der Haushaltsplan wurde inzwischen geändert. Bitte neu laden.")}
        )


def _ensure_draft(budget: Budget | None) -> None:
    if budget is not None and budget.status == Budget.Status.ADOPTED:
        raise BudgetError(
            {
                "status": gettext(
                    "Der Haushaltsplan ist beschlossen. Zum Ändern bitte zuerst wieder auf "
                    "Entwurf setzen."
                )
            }
        )


def _write(org, year: int, budget: Budget | None, lines: list[dict], user, note=None) -> Budget:
    if budget is None:
        budget = Budget.objects.create(organization=org, year=year, created_by=user)
    else:
        budget.version += 1
    if note is not None:
        budget.note = str(note).strip()[:2000]
    budget.save()
    budget.lines.all().delete()
    BudgetLine.objects.bulk_create(
        [
            BudgetLine(organization=org, budget=budget, position=i, **line)
            for i, line in enumerate(lines)
        ]
    )
    return budget


@transaction.atomic
def save(org, year: int, data: dict, user) -> tuple[Budget, dict]:
    """Ersetzt die Zeilen eines Entwurfs. Liefert den Plan und die Änderungen fürs Protokoll."""
    budget = _locked(org, year)
    _check_version(budget, data.get("version"))
    _ensure_draft(budget)
    lines = _clean_lines(org, data.get("lines", []))
    before = _summary(budget)
    budget = _write(org, year, budget, lines, user, data.get("note"))
    return budget, _changes(before, _summary(budget))


@transaction.atomic
def copy_previous(org, year: int, source: str, user, version=None) -> tuple[Budget, dict]:
    """Übernimmt Plan oder Ist des Vorjahres (auf volle Euro gerundet) in einen Entwurf."""
    budget = _locked(org, year)
    _check_version(budget, version)
    _ensure_draft(budget)
    if source == "plan":
        previous = Budget.objects.filter(organization=org, year=year - 1).first()
        if previous is None:
            raise BudgetError({"source": gettext("Für das Vorjahr gibt es keinen Plan.")})
        lines = [
            {
                "kind": ln.kind,
                "category_id": ln.category_id,
                "department_id": ln.department_id,
                "amount": ln.amount,
                "note": ln.note,
            }
            for ln in previous.lines.all()
        ]
    elif source == "actual":
        start, last = org.fiscal_range(year - 1)
        sums = actuals(org, start, last + datetime.timedelta(days=1))
        names = {c.pk: c.name.lower() for c in Category.objects.filter(organization=org)}
        lines = [
            {
                "kind": kind,
                "category_id": cat,
                "department_id": dept,
                "amount": value.quantize(Decimal("1"), ROUND_HALF_UP).quantize(Decimal("0.01")),
                "note": "",
            }
            for (cat, kind, dept), value in sorted(
                sums.items(), key=lambda kv: (kv[0][1] != "income", names.get(kv[0][0], ""))
            )
            if value > 0
        ]
        if not lines:
            raise BudgetError({"source": gettext("Im Vorjahr gibt es keine Buchungen.")})
    else:
        raise BudgetError({"source": gettext("Bitte Plan oder Ist wählen.")})
    before = _summary(budget)
    budget = _write(org, year, budget, lines, user)
    return budget, _changes(before, _summary(budget))


@transaction.atomic
def set_status(org, year: int, data: dict, user) -> tuple[Budget, dict]:
    budget = _locked(org, year)
    if budget is None:
        raise BudgetError({"status": gettext("Für dieses Jahr gibt es noch keinen Plan.")})
    _check_version(budget, data.get("version"))
    status = data.get("status")
    changes: dict = {}
    if status == Budget.Status.ADOPTED:
        raw = data.get("adopted_on") or ""
        try:
            adopted_on = datetime.date.fromisoformat(str(raw))
        except ValueError as exc:
            raise BudgetError(
                {"adopted_on": gettext("Bitte das Datum des Beschlusses angeben.")}
            ) from exc
        if adopted_on > _today():
            raise BudgetError({"adopted_on": gettext("Das Datum liegt in der Zukunft.")})
        if not budget.lines.exists():
            raise BudgetError({"status": gettext("Der Plan hat noch keine Zeilen.")})
        adopted_by = str(data.get("adopted_by") or "").strip()[:200]
        changes = {
            "Stand": [budget.get_status_display(), Budget.Status.ADOPTED.label],
            "beschlossen am": [
                budget.adopted_on.isoformat() if budget.adopted_on else "",
                adopted_on.isoformat(),
            ],
        }
        budget.status = Budget.Status.ADOPTED
        budget.adopted_on = adopted_on
        budget.adopted_by = adopted_by
    elif status == Budget.Status.DRAFT:
        changes = {"Stand": [budget.get_status_display(), Budget.Status.DRAFT.label]}
        budget.status = Budget.Status.DRAFT
    else:
        raise BudgetError({"status": gettext("Bitte Entwurf oder beschlossen wählen.")})
    budget.version += 1
    budget.save()
    return budget, changes


@transaction.atomic
def delete(org, year: int, version=None) -> Budget | None:
    budget = _locked(org, year)
    if budget is None:
        return None
    _check_version(budget, version)
    _ensure_draft(budget)
    budget.delete()
    return budget


def _summary(budget: Budget | None) -> dict:
    if budget is None:
        return {"Zeilen": "0", "Einnahmen": "0.00", "Ausgaben": "0.00"}
    sums = {
        row["kind"]: row["s"] or ZERO
        for row in budget.lines.values("kind").annotate(s=Sum("amount")).order_by()
    }
    return {
        "Zeilen": str(budget.lines.count()),
        "Einnahmen": str(sums.get("income", ZERO)),
        "Ausgaben": str(sums.get("expense", ZERO)),
    }


def _changes(before: dict, after: dict) -> dict:
    return {k: [before[k], after[k]] for k in after if before.get(k) != after[k]}
