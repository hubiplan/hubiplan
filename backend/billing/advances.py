"""Received advances are reconciled once, without creating another cash receipt."""

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.utils.translation import gettext

from finance.einvoice import _root

from . import einvoice_xml
from .einvoice_services import json_data, read_artifact
from .models import Invoice, InvoiceAdvance

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def ensure_unallocated(invoice):
    if invoice.final_allocations.filter(active=True).exists():
        raise ValidationError(gettext("Bitte zuerst die zugehörige Schlussrechnung stornieren."))


def split_amount(amount, weights):
    """Largest remainder distributes cents without creating or losing any money."""
    denominator = sum(weights, ZERO)
    exact = [amount * weight / denominator for weight in weights]
    result = [value.quantize(CENT, rounding=ROUND_DOWN) for value in exact]
    remainder = int((amount - sum(result, ZERO)) / CENT)
    order = sorted(
        range(len(weights)), key=lambda index: (exact[index] - result[index], -index), reverse=True
    )
    for index in order[:remainder]:
        result[index] += CENT
    return result


def snapshot(source, final):
    if (
        source.document_kind != "advance"
        or not source.electronic_data
        or source.status not in [Invoice.Status.OPEN, Invoice.Status.PAID]
        or source.partner_id != final.partner_id
        or source.project_id != final.project_id
        or source.date > final.date
    ):
        raise ValidationError(
            gettext(
                "Bitte eine passende, bezahlte Anzahlungsrechnung "
                "desselben Auftraggebers und Projekts wählen."
            )
        )
    ensure_unallocated(source)
    payments = list(
        source.payments.filter(booking__cancellation__isnull=True).order_by("date", "pk")
    )
    received = sum((row.amount for row in payments), ZERO)
    if (
        not 0 < received <= source.total
        or received != source.paid
        or any(row.date > final.date for row in payments)
    ):
        raise ValidationError(
            gettext(
                "Die Anzahlung ist nicht bezahlt oder die Zahlung liegt "
                "nach dem Schlussrechnungsdatum."
            )
        )
    root = _root(read_artifact(source))
    ns = einvoice_xml.NS
    if root.findtext(f"{{{ns['cbc']}}}InvoiceTypeCode") != "386":
        raise ValidationError(gettext("Das Original ist keine Anzahlungsrechnung."))
    groups = []
    for node in root.findall(f"{{{ns['cac']}}}TaxTotal/{{{ns['cac']}}}TaxSubtotal"):
        tax = node.find(f"{{{ns['cac']}}}TaxCategory")
        net = Decimal(node.findtext(f"{{{ns['cbc']}}}TaxableAmount"))
        vat = Decimal(node.findtext(f"{{{ns['cbc']}}}TaxAmount"))
        groups.append(
            {
                "category": tax.findtext(f"{{{ns['cbc']}}}ID"),
                "rate": tax.findtext(f"{{{ns['cbc']}}}Percent") or "0",
                "net": net,
                "tax": vat,
                "gross": net + vat,
            }
        )
    groups = [group for group in groups if group["gross"] > 0]
    if not groups or sum((g["gross"] for g in groups), ZERO) != source.total:
        raise ValidationError(gettext("Die Summen des Anzahlungsoriginals stimmen nicht überein."))
    for group, gross in zip(
        groups, split_amount(received, [g["gross"] for g in groups]), strict=True
    ):
        vat = (group["tax"] * gross / group["gross"]).quantize(CENT, rounding=ROUND_HALF_UP)
        group.update(gross=gross, tax=vat, net=gross - vat)
    return json_data(
        {
            "number": source.display_number,
            "date": source.date,
            "received": received,
            "groups": groups,
            "payments": [{"date": row.date, "amount": row.amount} for row in payments],
        }
    )


def prepare(invoice, identifiers, lines, lock=False):
    if invoice.document_kind != "final":
        if identifiers:
            raise ValidationError(
                gettext("Anzahlungen können nur in einer Schlussrechnung angerechnet werden.")
            )
        return []
    if not identifiers or len(set(identifiers)) != len(identifiers):
        raise ValidationError(gettext("Bitte Anzahlungsrechnungen genau einmal auswählen."))
    sources = (
        Invoice.objects.filter(organization=invoice.organization, pk__in=identifiers)
        .exclude(pk=invoice.pk)
        .order_by("pk")
    )
    if lock:
        sources = sources.select_for_update()
    sources = list(sources)
    if len(sources) != len(identifiers):
        raise ValidationError(gettext("Eine Anzahlungsrechnung ist nicht verfügbar."))
    results = [(source, snapshot(source, invoice)) for source in sources]
    totals = einvoice_xml.calculate(lines)
    limits = {(group["category"], Decimal(group["rate"])): group for group in totals["taxes"]}
    used = {}
    for _, info in results:
        for group in info["groups"]:
            key = (group["category"], Decimal(group["rate"]))
            aggregate = used.setdefault(key, {"net": ZERO, "tax": ZERO})
            for field in ["net", "tax"]:
                aggregate[field] += Decimal(group[field])
                if key not in limits or aggregate[field] > limits[key][field]:
                    raise ValidationError(
                        gettext(
                            "Die angerechneten Anzahlungen übersteigen die Schlussrechnung "
                            "oder ihre Steuergruppen."
                        )
                    )
    if sum((Decimal(info["received"]) for _, info in results), ZERO) > totals["gross"]:
        raise ValidationError(gettext("Die Anzahlungen übersteigen den Rechnungsbetrag."))
    return results


def save_references(invoice, values):
    invoice.advance_allocations.filter(active=False).delete()
    for source, info in values:
        InvoiceAdvance.objects.create(
            organization=invoice.organization,
            final_invoice=invoice,
            advance=source,
            amount=info["received"],
            snapshot=info,
            active=False,
        )


def reconcile(invoice):
    if invoice.document_kind != "final":
        return
    identifiers = list(invoice.advance_allocations.values_list("advance_id", flat=True))
    values = prepare(
        invoice, identifiers, [line.electronic_data for line in invoice.lines.all()], lock=True
    )
    ensure_current(invoice, values)
    for source, info in values:
        InvoiceAdvance.objects.filter(final_invoice=invoice, advance=source).update(
            active=True, amount=info["received"]
        )
        row = InvoiceAdvance.objects.get(final_invoice=invoice, advance=source)
        row.snapshot = info
        row.save(update_fields=["snapshot"])
        source.status = Invoice.Status.SETTLED
        source.save(update_fields=["status", "updated_at"])
    invoice.prepaid = sum((Decimal(info["received"]) for _, info in values), ZERO)
    if invoice.prepaid == invoice.total:
        invoice.status = Invoice.Status.PAID
    invoice.save(update_fields=["prepaid", "status", "updated_at"])


def release(invoice):
    from .services import _update_paid

    sources = list(
        Invoice.objects.select_for_update()
        .filter(final_allocations__final_invoice=invoice, final_allocations__active=True)
        .order_by("pk")
    )
    invoice.advance_allocations.filter(active=True).update(active=False)
    for source in sources:
        _update_paid(source)


def ensure_current(invoice, values=None):
    if invoice.document_kind != "final":
        return
    rows = {row.advance_id: row for row in invoice.advance_allocations.all()}
    if values is None:
        values = prepare(
            invoice, list(rows), [line.electronic_data for line in invoice.lines.all()]
        )
    if any(rows[source.pk].snapshot != info for source, info in values):
        raise ValidationError(
            gettext(
                "Die Anzahlung hat sich geändert. Bitte den Rechnungsentwurf "
                "erneut speichern und prüfen."
            )
        )


def notes(invoice):
    if invoice.document_kind != "final":
        return ""
    output = [gettext("Angerechnete Anzahlungen (bereits vereinnahmt):")]
    for row in invoice.advance_allocations.order_by("advance_id"):
        info = row.snapshot
        output.append(
            f"{info['number']} · {info['date']} · {gettext('Brutto')}: {info['received']} EUR"
        )
        for payment in info["payments"]:
            output.append(f"{gettext('Zahlung')}: {payment['date']} · {payment['amount']} EUR")
        for group in info["groups"]:
            output.append(
                f"{group['category']} / {group['rate']} % · "
                f"{gettext('Netto')}: {group['net']} EUR · "
                f"{gettext('Umsatzsteuer')}: {group['tax']} EUR"
            )
    return "\n".join(output)
