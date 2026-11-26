"""Auslagen in der Aufbewahrung der Kasse (finance/retention.py, docs/aufbewahrung.md).

Ausgezahlte Auslagen sind Teil der Buchführung: Ihre Belege sind die Belege der Buchung und
gehen mit ihnen nach 8 Jahren; Antrag, Verlauf und Sammelüberweisung werden mit den Büchern
nach 10 Jahren anonymisiert. Abgelehnte und zurückgezogene Anträge räumt
``services.purge`` (täglich) früher auf.
"""

from __future__ import annotations

from core.encfields import update_encrypted

ANON = "anonymisiert"


def purge_documents(org, bookings, delete_file) -> int:
    """Belegdateien ausgezahlter Auslagen dieser Buchungen entfernen."""
    from finance.models import Receipt as FinanceReceipt

    from .models import ExpenseClaim, ExpenseFile

    claims = ExpenseClaim.objects.filter(organization=org, booking__in=bookings)
    n = 0
    for row in ExpenseFile.objects.filter(organization=org, claim__in=claims).exclude(file=""):
        # Gemeinsame Datei mit dem Buchungsbeleg: den löscht die Kasse selbst
        if row.receipt_id is None and not FinanceReceipt.objects.filter(file=row.file.name).exists():
            delete_file(row.file)
        row.file = ""
        row.save(update_fields=["file"])
        n += 1
    return n


def anonymize(org, bookings) -> int:
    from .models import (
        ExpenseClaim,
        ExpenseEvent,
        ExpenseLine,
        TransferItem,
        TransferRun,
    )

    claims = ExpenseClaim.objects.filter(organization=org, booking__in=bookings)
    n = update_encrypted(
        claims, purpose=ANON, note="", name=ANON, email="", route="", payee={}, membership=None
    )
    update_encrypted(ExpenseLine.objects.filter(organization=org, claim__in=claims), text="")
    update_encrypted(
        ExpenseEvent.objects.filter(organization=org, claim__in=claims), who="", text=""
    )
    items = TransferItem.objects.filter(organization=org, claim__in=claims)
    update_encrypted(items, payee={"holder": ANON, "iban": "", "bic": ""})
    runs = TransferRun.objects.filter(organization=org, items__in=items).distinct()
    update_encrypted(runs.order_by(), debtor={"holder": ANON, "iban": "", "bic": ""})
    return n
