"""Leistungsrechnungen in die vorhandenen Rechnungs- und Zahlungsabläufe einbetten."""

import datetime
import hashlib
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils.translation import gettext

from finance.einvoice import as_json

from . import einvoice_validator, einvoice_xml
from .models import InvoiceArtifact, InvoiceLine


def json_data(value):
    # Anders als as_json beim Lesen dürfen Stückpreise und Mengen nicht auf 2 Stellen fallen.
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_data(item) for item in value]
    return value


def save_draft(invoice, data, partner, project):
    totals = einvoice_xml.calculate(data["lines"])
    if not 0 < totals["gross"] <= Decimal("9999999999.99"):
        raise ValidationError(
            gettext(
                "Der Rechnungsbetrag muss größer als 0 sein und innerhalb der Betragsgrenze liegen."
            )
        )
    if any(line["gross"] > Decimal("99999999.99") for line in totals["lines"]):
        raise ValidationError(gettext("Ein Positionsbetrag überschreitet die Betragsgrenze."))
    for key in ("date", "due_date", "subject", "note"):
        setattr(invoice, key, data[key])
    invoice.partner = partner
    invoice.recipient_kind = "partner"
    invoice.project = project
    invoice.total = totals["gross"]
    invoice.electronic_data = json_data(
        {
            key: value
            for key, value in data.items()
            if key
            not in {
                "lines",
                "partner",
                "payment_category",
                "project",
                "date",
                "due_date",
                "subject",
                "note",
            }
        }
    )
    buyer = data["buyer"]
    invoice.recipient_name = buyer["name"]
    invoice.recipient_address = (
        f"{buyer['street']}\n{buyer['postcode']} {buyer['city']}\n{buyer['country']}"
    )
    invoice.recipient_email = buyer["email"]
    invoice.save()
    invoice.lines.all().delete()
    for position, line in enumerate(totals["lines"]):
        InvoiceLine.objects.create(
            organization=invoice.organization,
            invoice=invoice,
            position=position,
            text=line["text"],
            amount=line["gross"],
            vat_rate=line["tax_rate"],
            electronic_data=json_data(line),
        )


def archive(invoice):
    """Erst erfolgreiche Prüfung, dann nummeriertes Original und lesbare Ansicht festhalten."""
    if hasattr(invoice, "performanceaccount"):
        account = invoice.performanceaccount
        if (
            invoice.partner_id != account.performance.customer_id
            or invoice.total != account.fee + account.travel + account.extras
        ):
            raise ValidationError(
                gettext("Kunde und Bruttobetrag müssen zur Auftrittsvereinbarung passen.")
            )
    xml = einvoice_xml.generate(invoice)
    report, report_xml = einvoice_validator.validate(xml)
    if report["status"] != "valid":
        messages = " ".join(item["text"] for item in report["messages"])
        raise ValidationError(
            {"electronic_data": messages or gettext("Die E-Rechnung ist ungültig.")}
        )
    artifact = InvoiceArtifact.objects.create(
        organization=invoice.organization,
        invoice=invoice,
        sha256=hashlib.sha256(xml).hexdigest(),
        report=report,
    )
    artifact.xml.save("invoice.xml", ContentFile(xml), save=False)
    artifact.report_xml.save("validation.xml", ContentFile(report_xml), save=False)
    artifact.save()
    from finance.einvoice import parse_xml, render

    readable = render(as_json(parse_xml(xml)), invoice.electronic_data["seller"]["name"])
    invoice.issued_pdf.save("invoice.pdf", ContentFile(readable), save=False)
    invoice.issued_pdf_sha256 = hashlib.sha256(readable).hexdigest()
    invoice.save(update_fields=["issued_pdf", "issued_pdf_sha256", "updated_at"])


def read_artifact(invoice, field="xml"):
    from .archive import documents_purged

    if documents_purged(invoice):
        raise ValidationError(gettext("Die Aufbewahrungsfrist dieser Rechnung ist abgelaufen."))
    artifact = InvoiceArtifact.objects.filter(
        invoice=invoice, organization=invoice.organization
    ).first()
    if artifact is None:
        raise ValidationError(
            gettext("Die Rechnung wurde noch nicht als E-Rechnung festgeschrieben.")
        )
    with getattr(artifact, field).open("rb") as stream:
        data = stream.read()
    expected = artifact.cancellation_sha256 if field == "cancellation_xml" else artifact.sha256
    if field in ("xml", "cancellation_xml") and hashlib.sha256(data).hexdigest() != expected:
        raise ValidationError(gettext("Die Prüfsumme des Rechnungsoriginals stimmt nicht."))
    return data


def archive_cancellation(invoice):
    import xml.etree.ElementTree as ET

    from finance.einvoice import _root

    original = _root(read_artifact(invoice))
    ns = einvoice_xml.NS
    original.tag = "{urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2}CreditNote"
    original.find(f"{{{ns['cbc']}}}ID").text = f"{invoice.display_number}-S"
    from django.utils import timezone

    original.find(f"{{{ns['cbc']}}}IssueDate").text = timezone.localdate().isoformat()
    due = original.find(f"{{{ns['cbc']}}}DueDate")
    if due is not None:
        original.remove(due)
    kind = original.find(f"{{{ns['cbc']}}}InvoiceTypeCode")
    kind.tag, kind.text = f"{{{ns['cbc']}}}CreditNoteTypeCode", "381"
    note = original.find(f"{{{ns['cbc']}}}Note")
    note.text = f"Storno zu {invoice.display_number}"
    for line in original.findall(f"{{{ns['cac']}}}InvoiceLine"):
        line.tag = f"{{{ns['cac']}}}CreditNoteLine"
        line.find(f"{{{ns['cbc']}}}InvoicedQuantity").tag = f"{{{ns['cbc']}}}CreditedQuantity"
    reference = ET.Element(f"{{{ns['cac']}}}BillingReference")
    document = einvoice_xml.element(reference, "cac:InvoiceDocumentReference")
    einvoice_xml.element(document, "cbc:ID", invoice.display_number)
    index = list(original).index(original.find(f"{{{ns['cac']}}}AccountingSupplierParty"))
    original.insert(index, reference)
    xml = ET.tostring(original, encoding="utf-8", xml_declaration=True)
    report, raw_report = einvoice_validator.validate(xml)
    if report["status"] != "valid":
        raise ValidationError(" ".join(item["text"] for item in report["messages"]))
    artifact = invoice.electronic_artifact
    artifact.cancellation_report = report
    artifact.cancellation_sha256 = hashlib.sha256(xml).hexdigest()
    artifact.cancellation_xml.save("cancellation.xml", ContentFile(xml), save=False)
    artifact.cancellation_report_xml.save(
        "cancellation-validation.xml", ContentFile(raw_report), save=False
    )
    artifact.save()
