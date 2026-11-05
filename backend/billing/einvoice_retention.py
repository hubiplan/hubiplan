"""E-Rechnungsdateien in die bestehende Aufbewahrung und Prüfexporte einbeziehen."""

from .models import (
    IncomingInvoice,
    IncomingValidation,
    InvoiceAdvance,
    InvoiceArtifact,
    InvoiceDelivery,
    InvoiceHybridArtifact,
)


def incoming_for_period(org, start, end):
    # Empfangsdatum ist auch bei verspätet eingehenden alten Rechnungen maßgeblich.
    return IncomingInvoice.objects.filter(
        organization=org, created_at__date__gte=start, created_at__date__lte=end
    )


def purge_files(org, start, end, delete_file):
    count = 0
    artifacts = InvoiceArtifact.objects.filter(
        organization=org, invoice__date__gte=start, invoice__date__lte=end
    )
    for row in artifacts:
        for field in ("xml", "report_xml", "cancellation_xml", "cancellation_report_xml"):
            if getattr(row, field):
                delete_file(getattr(row, field))
                setattr(row, field, "")
                count += 1
        row.save()
    for row in InvoiceHybridArtifact.objects.filter(
        organization=org, invoice__date__range=(start, end)
    ):
        for field in ("pdf", "xml", "cii_report", "pdf_report"):
            if getattr(row, field):
                delete_file(getattr(row, field))
                setattr(row, field, "")
                count += 1
        row.save()
    for row in incoming_for_period(org, start, end):
        for check in row.previous_checks.all():
            if check.report_xml:
                delete_file(check.report_xml)
                check.report_xml = ""
                check.save(update_fields=["report_xml"])
                count += 1
        for field in ("original", "xml", "report_xml"):
            if getattr(row, field):
                delete_file(getattr(row, field))
                setattr(row, field, "")
                count += 1
        row.save()
    return count


def anonymize(org, start, end):
    for row in InvoiceAdvance.objects.filter(
        organization=org, final_invoice__date__range=(start, end)
    ):
        row.snapshot = {}
        row.save(update_fields=["snapshot"])
    for row in InvoiceDelivery.objects.filter(organization=org, invoice__date__range=(start, end)):
        row.receipt = {}
        row.save(update_fields=["receipt"])
    IncomingValidation.objects.filter(incoming__in=incoming_for_period(org, start, end)).update(
        report={}
    )
    for row in InvoiceArtifact.objects.filter(
        organization=org, invoice__date__gte=start, invoice__date__lte=end
    ):
        row.report, row.cancellation_report = {}, {}
        row.save(update_fields=["report", "cancellation_report"])
    for row in incoming_for_period(org, start, end):
        row.data = {
            key: row.data[key]
            for key in ("net", "tax", "gross", "payable", "currency", "date")
            if key in row.data
        }
        row.report, row.review_note, row.name = {}, "", "Anonymisiert"
        row.save(update_fields=["data", "report", "review_note", "name"])


def export_table(org, start, end, add_file):
    from finance.gobd_export import Table, _columns, _stamp

    table = Table(
        "erechnungen.csv",
        "E-Rechnungen",
        "Originale und Prüfberichte",
        _columns(
            "Richtung",
            "Kennung",
            "Zeitpunkt",
            "Original",
            "SHA-256",
            "XML",
            "Prüfbericht",
            "Storno",
            "Stornoprüfung",
            "Status",
        ),
    )
    for row in InvoiceArtifact.objects.filter(
        organization=org, invoice__date__gte=start, invoice__date__lte=end
    ).select_related("invoice__organization"):
        prefix = f"erechnungen/ausgang/{row.pk}"
        paths = [
            add_file(f"{prefix}/{field}.xml", getattr(row, field)) if getattr(row, field) else ""
            for field in ("xml", "report_xml", "cancellation_xml", "cancellation_report_xml")
        ]
        table.add(
            "Ausgang",
            row.invoice.display_number,
            _stamp(row.created_at),
            paths[0],
            row.sha256,
            paths[0],
            *paths[1:],
            row.report.get("status", ""),
        )
    for row in incoming_for_period(org, start, end):
        prefix = f"erechnungen/eingang/{row.pk}"
        original = (
            add_file(
                f"{prefix}/original.{'pdf' if row.content_type == 'application/pdf' else 'xml'}",
                row.original,
            )
            if row.original
            else ""
        )
        xml = add_file(f"{prefix}/invoice.xml", row.xml) if row.xml else ""
        report = add_file(f"{prefix}/validation.xml", row.report_xml) if row.report_xml else ""
        table.add(
            "Eingang",
            row.pk,
            _stamp(row.created_at),
            original,
            row.sha256,
            xml,
            report,
            "",
            "",
            row.status,
        )
        for check in row.previous_checks.all():
            previous = (
                add_file(f"{prefix}/validation-{check.pk}.xml", check.report_xml)
                if check.report_xml
                else ""
            )
            table.add(
                "Vorprüfung",
                row.pk,
                _stamp(check.created_at),
                "",
                "",
                "",
                previous,
                "",
                "",
                check.report.get("status", ""),
            )
    for row in InvoiceHybridArtifact.objects.filter(
        organization=org, invoice__date__range=(start, end)
    ).select_related("invoice__organization"):
        prefix = f"erechnungen/zugferd/{row.pk}"
        paths = [
            add_file(f"{prefix}/{field}.{'pdf' if field == 'pdf' else 'xml'}", getattr(row, field))
            if getattr(row, field)
            else ""
            for field in ["pdf", "xml", "cii_report", "pdf_report"]
        ]
        table.add(
            "ZUGFeRD",
            row.invoice.display_number,
            _stamp(row.created_at),
            paths[0],
            row.sha256,
            paths[1],
            paths[2],
            "",
            paths[3],
            row.document,
        )
    for row in InvoiceDelivery.objects.filter(
        organization=org, invoice__date__range=(start, end)
    ).select_related("invoice__organization"):
        table.add(
            "Versand",
            row.invoice.display_number,
            _stamp(row.created_at),
            str(row.request_id),
            row.sha256,
            "",
            "",
            "",
            "",
            row.status,
        )
    for row in InvoiceAdvance.objects.filter(
        organization=org, final_invoice__date__range=(start, end)
    ).select_related("advance__organization", "final_invoice__organization"):
        table.add(
            "Anzahlung",
            row.final_invoice.display_number,
            _stamp(row.created_at),
            row.advance.display_number,
            "",
            "",
            "",
            "",
            "",
            f"{row.amount} / {row.active}",
        )
    return table
