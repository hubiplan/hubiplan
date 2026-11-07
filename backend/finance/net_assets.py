"""Vermögensübersicht zum Ende eines Geschäftsjahres (Konzept vereinskasse-steuern, S7).

Teil des Kassenberichts für die Mitgliederversammlung: Kontenstände, offene Forderungen aus
Rechnungen, Anlagevermögen mit Buchwert (Anlagenverzeichnis), offene Verbindlichkeiten aus
dem Rechnungseingang und davon in Rücklagen gebundene Mittel. Alles zum Stichtag: was erst
nach dem Jahresende bezahlt wurde, war am Stichtag noch offen.
"""

from __future__ import annotations

import datetime
from decimal import Decimal, InvalidOperation

from django.db.models import Sum
from django.utils import timezone

from access.modules import module_on

from . import services
from .models import Account, Reserve

ZERO = Decimal("0.00")


def _receivables(org, last: datetime.date) -> dict:
    """Offene Rechnungen an Mitglieder und Geschäftspartner zum Stichtag (nur Summen)."""
    from billing.models import Invoice, Payment

    invoices = list(
        Invoice.objects.filter(organization=org, date__lte=last).exclude(
            status__in=[Invoice.Status.DRAFT, Invoice.Status.CANCELLED, Invoice.Status.SETTLED]
        )
    )
    paid = {
        row["invoice_id"]: row["s"] or ZERO
        for row in Payment.objects.filter(invoice__in=invoices, date__lte=last)
        .values("invoice_id")
        .annotate(s=Sum("amount"))
        .order_by()
    }
    total, count = ZERO, 0
    for inv in invoices:
        open_amount = inv.total - inv.prepaid - paid.get(inv.pk, ZERO)
        if open_amount > 0:
            total += open_amount
            count += 1
    return {"total": total, "count": count}


def _amount(value) -> Decimal | None:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _liabilities(org, last: datetime.date) -> dict:
    """Eingangsrechnungen bis zum Stichtag, die am Stichtag noch nicht bezahlt waren."""
    from billing.models import IncomingInvoice

    rows = []
    qs = (
        IncomingInvoice.objects.filter(organization=org)
        .exclude(status="rejected")
        .select_related("booking")
    )
    for item in qs:
        data = item.data or {}
        if data.get("credit_note") or data.get("currency", "EUR") != "EUR":
            continue
        try:
            issued = datetime.date.fromisoformat(str(data.get("date") or ""))
        except ValueError:
            issued = timezone.localdate(item.created_at)
        if issued > last:
            continue
        if item.booking_id and item.booking.date <= last:
            continue
        amount = _amount(data.get("payable"))
        if amount is None or amount <= 0:
            continue
        due = None
        try:
            due = datetime.date.fromisoformat(str(data.get("due_date") or ""))
        except ValueError:
            pass
        rows.append(
            {
                "seller": str(data.get("seller") or ""),
                "number": str(data.get("number") or ""),
                "date": issued,
                "due_date": due,
                "amount": amount,
            }
        )
    rows.sort(key=lambda r: (r["due_date"] or r["date"], r["seller"].casefold()))
    return {"total": sum((r["amount"] for r in rows), ZERO), "count": len(rows), "items": rows}


def report(org, year: int) -> dict:
    start, last = org.fiscal_range(year)
    balances = services.balances(org.pk, before=last + datetime.timedelta(days=1))
    accounts = [
        {"id": a.pk, "name": a.name, "kind": a.kind, "balance": balances.get(a.pk, ZERO)}
        for a in Account.objects.filter(organization=org, opening_date__lte=last)
        if a.is_active or balances.get(a.pk, ZERO)
    ]
    cash = sum((a["balance"] for a in accounts), ZERO)
    receivables = _receivables(org, last)
    liabilities = _liabilities(org, last)
    fixed = None
    if module_on(org, "tax"):
        from . import assets

        register = assets.register(org, year)
        if register["rows"]:
            fixed = {
                "total": register["totals"]["book_end"],
                "count": sum(1 for r in register["rows"] if r["book_end"]),
            }
    reserves = None
    if org.reserves_on:
        from . import reserves as reserve_logic

        sums = reserve_logic.balances(org, until=last)
        names = dict(Reserve.objects.filter(organization=org).values_list("pk", "name"))
        items = [{"name": names[pk], "balance": value} for pk, value in sums.items() if value]
        reserves = {
            "total": sum((r["balance"] for r in items), ZERO),
            "items": sorted(items, key=lambda r: r["name"].casefold()),
        }
    total = cash + receivables["total"] + (fixed["total"] if fixed else ZERO)
    net = total - liabilities["total"]
    bound = reserves["total"] if reserves else ZERO
    return {
        "year": year,
        "label": org.fiscal_label(year),
        "start_date": start,
        "end_date": last,
        "accounts": accounts,
        "cash": cash,
        "receivables": receivables,
        "fixed_assets": fixed,
        "liabilities": liabilities,
        "assets_total": total,
        "net": net,
        "reserves": reserves,
        "free": net - bound,
    }
