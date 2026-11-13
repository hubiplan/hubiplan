"""Ende der Aufbewahrungsfrist (Finanzamt-Prüfung C6).

Nach § 147 AO (Fassung ab 2025) sind Buchungsbelege 8 Jahre, Bücher und Abschlüsse
10 Jahre aufzubewahren. Maßgeblich sind Belegentstehung, letzte Bucheintragung und
Aufstellung des Abschlusses; spätere Erfassungen verschieben die Jahresfristen.

Zwei Stufen je abgeschlossenem Geschäftsjahr, beide von Hand ausgelöst:

1. **Belege** (ab Beginn des 9. Jahres): Belegdateien, archivierte Rechnungs-, Quittungs-,
   Zuwendungs- und Zählprotokoll-PDFs, Kontoauszugsdateien, SEPA-Dateien und
   Unterschriften werden gelöscht.
2. **Bücher** (ab Beginn des 11. Jahres): Namen, Anschriften, Texte und Bankdaten werden
   anonymisiert. Beträge, Daten, Konten, Kategorien und Nummern bleiben, damit Bestände und
   Vorjahresvergleiche weiter stimmen. Protokolleinträge dieser Daten werden geleert
   (die Protokollkette bleibt prüfbar).

Die Fristen stehen fest im Code und lassen sich nicht verkürzen. Verlängern lässt sich die
Aufbewahrung je Geschäftsjahr mit einer Löschsperre (z. B. laufende Betriebsprüfung,
Rechtsstreit, Fachfrage FQ10); solange sie gilt, löscht ``purge`` nichts.
Übersicht aller Datenarten: docs/aufbewahrung.md.
"""

from __future__ import annotations

import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import CharField, Max
from django.db.models.functions import Cast
from django.utils import timezone
from django.utils.translation import gettext

from core.encfields import update_encrypted

from . import bank_originals

ANON = "anonymisiert"
DOCUMENT_YEARS = 8
RECORD_YEARS = 10


def due_dates(org, year: int) -> tuple[datetime.date, datetime.date]:
    """Konservative Jahresfristen nach Entstehung und letzter Bucheintragung."""
    from audit.log import OBJECT_TYPES
    from audit.models import AuditEntry
    from billing.models import (
        DebitRun,
        Dunning,
        IncomingInvoice,
        IncomingValidation,
        Invoice,
        InvoiceAdvance,
        InvoiceArtifact,
        InvoiceDelivery,
        InvoiceHybridArtifact,
    )

    from .models import (
        Booking,
        CashCount,
        CashReceipt,
        Donation,
        DonationStatement,
        Receipt,
        ReserveMovement,
        YearClosing,
    )

    start, end = org.fiscal_range(year)
    from music.models import (
        EngagementDocument,
        MusicianClaim,
        PayoutRun,
        PerformanceAccount,
        PerformanceExpense,
    )

    document_year = record_year = end.year
    sources = [
        (EngagementDocument, "created_at__date"),
        (PayoutRun, "execution_date"),
        (PerformanceAccount, "date"),
        (MusicianClaim, "assignment__performance__performanceaccount__date"),
        (PerformanceExpense, "booking__date"),
        (IncomingInvoice, "created_at__date"),
        (IncomingValidation, "incoming__created_at__date"),
        (InvoiceArtifact, "invoice__date"),
        (InvoiceAdvance, "final_invoice__date"),
        (InvoiceDelivery, "invoice__date"),
        (InvoiceHybridArtifact, "invoice__date"),
        (Booking, "date"),
        (Invoice, "date"),
        (Dunning, "date"),
        (CashCount, "date"),
        (CashReceipt, "receipt_date"),
        (Donation, "date"),
        (DonationStatement, "issued_on"),
        (ReserveMovement, "date"),
        (DebitRun, "collection_date"),
    ]
    for model, field in sources:
        rows = model.objects.filter(
            organization=org, **{f"{field}__gte": start, f"{field}__lte": end}
        )
        latest = rows.aggregate(latest=Max("created_at"))["latest"]
        if latest:
            document_year = max(document_year, timezone.localdate(latest).year)
        # Korrekturen gehören zur letzten Eintragung, nicht nur zur Ersterfassung.
        latest_change = AuditEntry.objects.filter(
            organization=org,
            object_type=OBJECT_TYPES.get(model._meta.model_name, model._meta.model_name),
            object_id__in=rows.annotate(export_id=Cast("pk", CharField())).values("export_id"),
        ).aggregate(latest=Max("timestamp"))["latest"]
        if latest_change:
            record_year = max(record_year, timezone.localdate(latest_change).year)
            # Ein Entwurf kann erst in einem späteren Jahr ausgegeben werden.
            if model in (Invoice, IncomingInvoice, PerformanceAccount, MusicianClaim):
                document_year = max(document_year, timezone.localdate(latest_change).year)
    for rows in (
        Receipt.objects.filter(organization=org, booking__date__gte=start, booking__date__lte=end),
        bank_originals.for_year(org, start, end),
    ):
        latest = rows.aggregate(latest=Max("created_at"))["latest"]
        if latest:
            document_year = max(document_year, timezone.localdate(latest).year)
    # A later final invoice keeps the underlying advance evidence for at least
    # as long as the reconciliation, including delayed issue/cancellation.
    latest_final = InvoiceAdvance.objects.filter(
        organization=org, advance__date__gte=start, advance__date__lte=end
    ).aggregate(latest=Max("final_invoice__updated_at"))["latest"]
    if latest_final:
        document_year = max(document_year, timezone.localdate(latest_final).year)
    closed = YearClosing.objects.filter(organization=org, year=year).aggregate(
        latest=Max("closed_at")
    )["latest"]
    if closed:
        record_year = max(record_year, timezone.localdate(closed).year)
    record_year = max(record_year, document_year)
    return (
        datetime.date(document_year + DOCUMENT_YEARS + 1, 1, 1),
        datetime.date(record_year + RECORD_YEARS + 1, 1, 1),
    )


def _today() -> datetime.date:
    return timezone.localdate()


def state(org, closing) -> dict:
    today = _today()
    docs_from, records_from = due_dates(org, closing.year)
    pending_originals = False
    if closing.documents_purged_at is not None and today >= docs_from:
        start, end = org.fiscal_range(closing.year)
        pending_originals = bank_originals.for_year(org, start, end).exists()
    return {
        "documents_from": docs_from,
        "records_from": records_from,
        "documents_purged_at": closing.documents_purged_at,
        "records_purged_at": closing.records_purged_at,
        "purged_by": closing.purged_by_name,
        "documents_due": today >= docs_from
        and (closing.documents_purged_at is None or pending_originals),
        "records_due": closing.records_purged_at is None and today >= records_from,
        # Löschsperre (Fachfrage FQ10)
        "hold": closing.retention_hold,
        "hold_by": closing.retention_hold_by_name,
        "hold_at": closing.retention_hold_at,
    }


def set_hold(org, year: int, reason: str, user) -> None:
    """Löschsperre setzen (Grund) oder aufheben (leerer Grund). Wird protokolliert."""
    from audit.log import record

    from .models import YearClosing
    from .services import lock_bank_sources

    reason = (reason or "").strip()[:500]
    with transaction.atomic():
        lock_bank_sources(org)
        closing = (
            YearClosing.objects.select_for_update().filter(organization=org, year=year).first()
        )
        if closing is None:
            raise ValidationError(
                gettext("Eine Löschsperre gibt es nur für abgeschlossene Geschäftsjahre.")
            )
        if closing.records_purged_at:
            raise ValidationError(gettext("Dieses Geschäftsjahr ist schon bereinigt."))
        old = closing.retention_hold
        if old == reason:
            return
        closing.retention_hold = reason
        closing.retention_hold_by_name = (
            (user.get_full_name() or user.email)[:200] if reason else ""
        )
        closing.retention_hold_at = timezone.now() if reason else None
        closing.save(
            update_fields=["retention_hold", "retention_hold_by_name", "retention_hold_at"]
        )
        record(org, user, "update", closing, {"Löschsperre": [old or None, reason or None]})


def _delete_file(field) -> None:
    """Datei erst nach dem Commit löschen: Rollt die Bereinigung zurück, bleibt der Beleg
    (Gesamtaudit 01.11., GA-F07)."""
    from core.files import delete_on_commit

    delete_on_commit(field)


def _purge_documents(org, year, start, end) -> dict[str, int]:
    from billing.models import DebitRun, Dunning, Invoice

    from .models import (
        BankStatement,
        Booking,
        CashCount,
        CashReceipt,
        DonationStatement,
        Receipt,
        YearClosing,
    )

    originals = list(bank_originals.for_year(org, start, end))
    if originals:
        held_years = list(
            YearClosing.objects.filter(organization=org)
            .exclude(retention_hold="")
            .order_by("year")
            .values_list("year", flat=True)
        )
        for statement in originals:
            first, last = bank_originals.year_range(org, statement)
            held = next((year for year in held_years if first <= year <= last), None)
            if held is not None:
                raise ValidationError(
                    gettext(
                        "Der Kontoauszug betrifft auch das Geschäftsjahr {year} mit Löschsperre. "
                        "Die Bereinigung wurde abgebrochen."
                    ).format(year=org.fiscal_label(held))
                )

    counts: dict[str, int] = {}
    bookings = Booking.objects.filter(organization=org, date__gte=start, date__lte=end)
    receipts = Receipt.objects.filter(organization=org, booking__in=bookings)
    # Quittungen verweisen auf ihre PDFs (RESTRICT): Verweise und Unterschriften zuerst
    cash = CashReceipt.objects.filter(organization=org, booking__in=bookings)
    counts["Unterschriften"] = cash.update(
        document=None, cancel_document=None, treasurer_signature=None, counterparty_signature=None
    )
    cash_other = CashReceipt.objects.filter(
        organization=org, cancel_document__in=receipts
    ) | CashReceipt.objects.filter(organization=org, document__in=receipts)
    cash_other.update(document=None, cancel_document=None)
    n = 0
    for r in receipts:
        _delete_file(r.file)
        n += 1
    # Aufbewahrungsfrist abgelaufen: Freigabe prüft die Datenbank (finance/0032)
    from . import gobd

    gobd.release_documents(org.pk, year, start, end)
    receipts.delete()
    counts["Belege"] = n

    n = 0
    for i in Invoice.objects.filter(organization=org, date__gte=start, date__lte=end).exclude(
        issued_pdf=""
    ):
        _delete_file(i.issued_pdf)
        i.issued_pdf = ""
        i.save(update_fields=["issued_pdf"])
        n += 1
    for i in Invoice.objects.filter(organization=org, date__gte=start, date__lte=end).exclude(
        cancellation_pdf=""
    ):
        _delete_file(i.cancellation_pdf)
        i.cancellation_pdf = ""
        i.save(update_fields=["cancellation_pdf"])
        n += 1
    counts["Rechnungs-PDFs"] = n
    from billing.einvoice_retention import purge_files

    counts["E-Rechnungsdateien"] = purge_files(org, start, end, _delete_file)
    from music.models import EngagementDocument

    for document in EngagementDocument.objects.filter(
        organization=org, created_at__date__range=(start, end)
    ).exclude(file=""):
        _delete_file(document.file)
        document.file = ""
        document.save(update_fields=["file"])

    n = 0
    for d in Dunning.objects.filter(organization=org, date__gte=start, date__lte=end).exclude(
        issued_pdf=""
    ):
        _delete_file(d.issued_pdf)
        d.issued_pdf = ""
        d.save(update_fields=["issued_pdf"])
        n += 1
    counts["Mahnungs-PDFs"] = n

    n = 0
    for s in DonationStatement.objects.filter(
        organization=org, issued_on__gte=start, issued_on__lte=end
    ).exclude(file=""):
        _delete_file(s.file)
        s.file = ""
        s.save(update_fields=["file"])
        n += 1
    counts["Zuwendungsbestätigungen"] = n

    n = 0
    for cc in CashCount.objects.filter(organization=org, date__gte=start, date__lte=end).exclude(
        pdf=""
    ):
        _delete_file(cc.pdf)
        cc.pdf = ""
        cc.save(update_fields=["pdf"])
        n += 1
    counts["Zählprotokolle"] = n

    n = 0
    purged_ids = [st.pk for st in originals]
    for st in originals:
        # Mehrere Auszüge können dieselbe Datei teilen (BP-S01): erst löschen, wenn kein
        # Auszug außerhalb dieses Jahres sie noch braucht
        shared = (
            BankStatement.objects.filter(organization=org, source=st.source.name)
            .exclude(pk__in=purged_ids)
            .exists()
        )
        if not shared:
            _delete_file(st.source)
        st.source = ""
        st.save(update_fields=["source"])
        n += 1
    counts["Kontoauszugsdateien"] = n

    counts["SEPA-Dateien"] = (
        DebitRun.objects.filter(
            organization=org, collection_date__gte=start, collection_date__lte=end
        )
        .exclude(xml="")
        .update(xml="")
    )
    return counts


def _anonymize_records(org, start, end) -> dict[str, int]:
    from audit.log import OBJECT_TYPES
    from audit.models import AuditEntry
    from billing.models import Dunning, Invoice, InvoiceLine

    from .models import (
        BankLine,
        Booking,
        CashCount,
        CashReceipt,
        Donation,
        DonationStatement,
        ReserveMovement,
    )

    counts: dict[str, int] = {}
    touched: dict[str, list] = {}

    def ids(qs, label):
        touched[label] = [str(pk) for pk in qs.values_list("pk", flat=True)]
        return qs

    bookings = ids(
        Booking.objects.filter(organization=org, date__gte=start, date__lte=end), "booking"
    )
    counts["Buchungen"] = update_encrypted(
        bookings,
        text=ANON,
        counterparty="",
        partner=None,
        reference="",
        membership=None,
        cancel_reason="",
    )
    invoices = ids(
        Invoice.objects.filter(organization=org, date__gte=start, date__lte=end), "invoice"
    )
    Dunning.objects.filter(invoice__in=invoices).update(text="")
    # Mitgliedsrechnungen brauchen sonst ein Mitglied (Constraint rechnung_empfaenger)
    invoices.filter(
        recipient_kind__in=[
            Invoice.Recipient.MEMBER,
            Invoice.Recipient.PARTNER,
            Invoice.Recipient.HOUSEHOLD,
        ]
    ).update(
        recipient_kind=Invoice.Recipient.ANONYMIZED, membership=None, partner=None, household=None
    )
    counts["Rechnungen"] = update_encrypted(
        invoices,
        recipient_name=ANON,
        recipient_address="",
        recipient_email="",
        note="",
        membership=None,
        electronic_data={},
    )
    from billing.einvoice_retention import anonymize, incoming_for_period

    ids(incoming_for_period(org, start, end), "incominginvoice")
    anonymize(org, start, end)
    from music.models import (
        EngagementDocument,
        MusicianClaim,
        PayoutItem,
        PayoutRun,
        PerformanceAccount,
    )

    update_encrypted(
        ids(
            EngagementDocument.objects.filter(
                organization=org, created_at__date__range=(start, end)
            ),
            "engagementdocument",
        ),
        snapshot={},
        acceptance_note="",
        resolution_note="",
    )

    payout_runs = PayoutRun.objects.filter(organization=org, execution_date__range=(start, end))
    update_encrypted(ids(payout_runs, "payoutrun"), debtor={"holder": ANON, "iban": "", "bic": ""})
    update_encrypted(
        ids(PayoutItem.objects.filter(organization=org, run__in=payout_runs), "payoutitem"),
        payee={"holder": ANON, "iban": "", "bic": ""},
    )

    update_encrypted(
        ids(
            PerformanceAccount.objects.filter(organization=org, date__range=(start, end)),
            "performanceaccount",
        ),
        note="",
    )
    update_encrypted(
        ids(
            MusicianClaim.objects.filter(
                organization=org,
                assignment__performance__performanceaccount__date__range=(start, end),
            ),
            "musicianclaim",
        ),
        note="",
    )
    commercial_lines = InvoiceLine.objects.filter(invoice__in=invoices).exclude(electronic_data={})
    update_encrypted(commercial_lines, text=ANON, detail="")
    update_encrypted(InvoiceLine.objects.filter(invoice__in=invoices), electronic_data={})
    # Posten nennen in Sammelrechnungen Mitglieder mit Namen (Audit 02.11. BP-F03)
    counts["Rechnungsposten"] = update_encrypted(
        InvoiceLine.objects.filter(invoice__in=invoices, membership__isnull=False),
        text=ANON,
        detail="",
        membership=None,
    )
    InvoiceLine.objects.filter(invoice__in=invoices).exclude(detail="").update(detail="")
    counts["Quittungen"] = update_encrypted(
        ids(CashReceipt.objects.filter(organization=org, booking__in=bookings), "cashreceipt"),
        counterparty_name=ANON,
        counterparty_address="",
        email="",
        purpose=ANON,
        membership=None,
        counterparty_confirmed="",
        no_signature_reason="",
        cancel_reason="",
        treasurer_signature=None,
        counterparty_signature=None,
    )
    counts["Zuwendungen"] = update_encrypted(
        ids(Donation.objects.filter(organization=org, date__gte=start, date__lte=end), "donation"),
        donor_name=ANON,
        donor_address="",
        note="",
        membership=None,
    )
    counts["Zuwendungsbestätigungen"] = update_encrypted(
        ids(
            DonationStatement.objects.filter(
                organization=org, issued_on__gte=start, issued_on__lte=end
            ),
            "donationstatement",
        ),
        donor_name=ANON,
        donor_address="",
        membership=None,
        items=[],
        cancel_reason="",
    )
    counts["Kontoumsätze"] = ids(
        BankLine.objects.filter(organization=org, date__gte=start, date__lte=end), "bankline"
    ).update(name="", iban="", purpose="", details=[], suggested_membership=None)
    counts["Kassenzählungen"] = update_encrypted(
        ids(
            CashCount.objects.filter(organization=org, date__gte=start, date__lte=end), "cashcount"
        ),
        counted_by=ANON,
        witness="",
        note="",
    )
    counts["Rücklagenbewegungen"] = ids(
        ReserveMovement.objects.filter(organization=org, date__gte=start, date__lte=end),
        "reservemovement",
    ).update(note="", created_by_name="", created_by=None)

    # Protokolleinträge dieser Daten leeren (Kette bleibt prüfbar, siehe audit/chain.py)
    cleared = 0
    for model, pks in touched.items():
        if pks:
            cleared += AuditEntry.objects.filter(
                organization=org, object_type=OBJECT_TYPES.get(model, model), object_id__in=pks
            ).update(changes={}, object_repr=ANON, cleared=True)
    counts["Protokolleinträge"] = cleared
    return counts


@transaction.atomic
def purge(org, year: int, user) -> dict:
    """Führt aus, was für das Geschäftsjahr fällig ist; gibt die Anzahlen zurück."""
    from audit.log import record

    from .models import YearClosing
    from .services import lock_bank_sources

    lock_bank_sources(org)

    closing = YearClosing.objects.select_for_update().filter(organization=org, year=year).first()
    if closing is None:
        raise ValidationError(gettext("Nur abgeschlossene Geschäftsjahre lassen sich bereinigen."))
    info = state(org, closing)
    if closing.retention_hold:
        raise ValidationError(
            gettext("Für dieses Geschäftsjahr gilt eine Löschsperre: {x}").format(
                x=closing.retention_hold
            )
        )
    if not (info["documents_due"] or info["records_due"]):
        raise ValidationError(
            gettext(
                "Die Aufbewahrungsfrist läuft noch: Belege ab {x:%d.%m.%Y}, Bücher ab "
                "{x2:%d.%m.%Y}."
            ).format(x=info["documents_from"], x2=info["records_from"])
        )
    start, end = org.fiscal_range(year)
    counts: dict[str, int] = {}
    now = timezone.now()
    if info["documents_due"]:
        counts.update(_purge_documents(org, year, start, end))
        closing.documents_purged_at = now
    if info["records_due"]:
        counts.update(_anonymize_records(org, start, end))
        closing.records_purged_at = now
    closing.purged_by_name = (user.get_full_name() or user.email)[:200]
    closing.save(update_fields=["documents_purged_at", "records_purged_at", "purged_by_name"])
    what = "Belege gelöscht" if not info["records_due"] else "Belege gelöscht, Bücher anonymisiert"
    if info["records_due"] and not info["documents_due"]:
        what = "Bücher anonymisiert"
    record(
        org,
        user,
        "update",
        closing,
        {
            "Aufbewahrungsfrist abgelaufen": [
                None,
                f"Geschäftsjahr {org.fiscal_label(year)}: {what}",
            ],
            **{k: [None, v] for k, v in counts.items() if v},
        },
    )
    return {"done": what, "counts": counts}
