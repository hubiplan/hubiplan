"""Versand von Rechnungen, Stornos, Mahnungen und Vorabankündigungen per E-Mail."""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

from organizations.addresses import base_url
from outbox import mail

from . import pdf
from .archive import archived_cancellation, archived_dunning, archived_pdf, documents_purged
from .models import (
    DebitItem,
    Dunning,
    Invoice,
)


def _as_drf(exc: DjangoValidationError) -> serializers.ValidationError:
    if hasattr(exc, "message_dict"):
        return serializers.ValidationError(exc.message_dict)
    return serializers.ValidationError({"detail": " ".join(exc.messages)})


# --- Versand ---


def send_invoice(invoice: Invoice) -> bool:
    if not invoice.recipient_email or invoice.status != Invoice.Status.OPEN:
        return False
    org = invoice.organization
    body = (
        f"Guten Tag,\n\n"
        f"anbei erhalten Sie die Rechnung {invoice.display_number} von {org.name} "
        f"über {pdf.euro(invoice.outstanding)}, zahlbar bis {invoice.due_date:%d.%m.%Y}.\n\n"
        f"Betreff: {invoice.subject}\n\n"
    )
    if invoice.recipient_kind == Invoice.Recipient.MEMBER and org.member_portal_enabled:
        body += f"Im Mitgliederbereich sehen Sie Ihre Rechnungen jederzeit: {base_url(org)}\n\n"
    body += f"Viele Grüße\n{org.name}\n"
    attachments = [(pdf.filename(invoice), archived_pdf(invoice), "application/pdf")]
    if invoice.electronic_data:
        from .einvoice_services import read_artifact

        try:
            attachments.insert(
                0, (f"{invoice.display_number}.xml", read_artifact(invoice), "application/xml")
            )
        except DjangoValidationError as exc:
            raise _as_drf(exc) from exc
    sent = mail.send(
        invoice.recipient_email,
        f"Rechnung {invoice.display_number} – {org.name}",
        body,
        organization=org,
        kind="rechnung",
        attachments=attachments,
        reply_to=[org.contact_email] if org.contact_email else None,
        fail_silently=True,
    )
    if sent:
        invoice.sent_at = timezone.now()
        invoice.save(update_fields=["sent_at", "updated_at"])
    return sent


def send_cancellation(invoice: Invoice) -> bool:
    """Stornorechnung per E-Mail an den Empfänger (bei E-Rechnungen mit XML)."""
    content = archived_cancellation(invoice)
    if content is None or not invoice.recipient_email:
        return False
    org = invoice.organization
    body = (
        f"Guten Tag,\n\n"
        f"anbei erhalten Sie die Stornorechnung {invoice.cancellation_number} von {org.name}. "
        f"Sie hebt die Rechnung {invoice.display_number} vom {invoice.date:%d.%m.%Y} "
        f"vollständig auf.\n\n"
    )
    if invoice.cancel_reason:
        body += f"Grund: {invoice.cancel_reason}\n\n"
    body += f"Viele Grüße\n{org.name}\n"
    attachments = [(pdf.cancellation_filename(invoice), content, "application/pdf")]
    if invoice.electronic_data:
        from .einvoice_services import read_artifact

        try:
            attachments.insert(
                0,
                (
                    f"{invoice.cancellation_number}.xml",
                    read_artifact(invoice, "cancellation_xml"),
                    "application/xml",
                ),
            )
        except DjangoValidationError as exc:
            raise _as_drf(exc) from exc
    sent = mail.send(
        invoice.recipient_email,
        f"Stornorechnung {invoice.cancellation_number} – {org.name}",
        body,
        organization=org,
        kind="rechnung",
        attachments=attachments,
        reply_to=[org.contact_email] if org.contact_email else None,
        fail_silently=True,
    )
    if sent:
        invoice.cancellation_sent_at = timezone.now()
        invoice.save(update_fields=["cancellation_sent_at", "updated_at"])
    return sent


def combined_pdf(invoices: list[Invoice]) -> bytes:
    """Mehrere Rechnungen in einem PDF, jede in ihrer ausgegebenen Fassung (Audit 02.11.
    BP-F02). Nach Fristablauf gelöschte fehlen; Entwürfe werden frisch erzeugt."""
    parts = [archived_pdf(i) for i in invoices if i.issued_pdf or not documents_purged(i)]
    return merge_pdf_parts(parts)


def merge_pdf_parts(parts: list[bytes]) -> bytes:
    import io

    import pypdfium2 as pdfium

    if len(parts) == 1:
        return parts[0]
    out = pdfium.PdfDocument.new()
    try:
        for data in parts:
            doc = pdfium.PdfDocument(data)
            try:
                out.import_pages(doc)
            finally:
                doc.close()
        buffer = io.BytesIO()
        out.save(buffer)
        return buffer.getvalue()
    finally:
        out.close()


def send_dunning(dunning: Dunning) -> bool:
    invoice = dunning.invoice
    if not invoice.recipient_email:
        return False
    org = invoice.organization
    body = (
        f"Guten Tag,\n\n"
        f"zu der Rechnung {invoice.display_number} vom {invoice.date:%d.%m.%Y} "
        f"ist noch ein Betrag von {pdf.euro(invoice.outstanding)} offen. "
        f"Bitte überweisen Sie ihn bis zum {dunning.due_date:%d.%m.%Y}.\n\n"
        f"Die Einzelheiten stehen im angehängten Schreiben ({dunning.name}). "
        f"Falls Sie inzwischen bezahlt haben, betrachten Sie diese Nachricht bitte "
        f"als gegenstandslos.\n\n"
        f"Viele Grüße\n{org.name}\n"
    )
    sent = mail.send(
        invoice.recipient_email,
        f"{dunning.name}: Rechnung {invoice.display_number} – {org.name}",
        body,
        organization=org,
        kind="mahnung",
        attachments=[
            (
                pdf.dunning_filename(dunning),
                archived_dunning(dunning),
                "application/pdf",
            )
        ],
        reply_to=[org.contact_email] if org.contact_email else None,
        fail_silently=True,
    )
    if sent:
        dunning.sent_at = timezone.now()
        dunning.save(update_fields=["sent_at"])
    return sent


def send_prenotification(item: DebitItem) -> bool:
    invoice = item.invoice
    if not invoice.recipient_email:
        return False
    org = invoice.organization
    body = f"Guten Tag,\n\n{pdf.prenotification_text(item)}\n\nViele Grüße\n{org.name}\n"
    sent = mail.send(
        invoice.recipient_email,
        f"Ankündigung SEPA-Lastschrift {item.run.collection_date:%d.%m.%Y} – {org.name}",
        body,
        organization=org,
        kind="vorabankuendigung",
        reply_to=[org.contact_email] if org.contact_email else None,
        fail_silently=True,
    )
    if sent:
        item.prenotified_at = timezone.now()
        item.save(update_fields=["prenotified_at"])
    return sent
