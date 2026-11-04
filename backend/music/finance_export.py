"""Prüfexport und Aufbewahrung der Abrechnungsdaten."""

from .models import MusicianClaim, PerformanceAccount, PerformanceExpense


def export_tables(org, start, end):
    from finance.gobd_export import Table, _columns

    accounts = PerformanceAccount.objects.filter(
        organization=org, performance__event__starts_at__date__range=(start, end)
    )
    table = Table(
        "auftritte.csv",
        "Auftrittsabrechnungen",
        "Vereinbarte Bruttobeträge in EUR",
        _columns(
            "Kennung",
            "Auftritt",
            "Honorar",
            "Fahrtkosten",
            "Weitere Leistungen",
            "Rechnung",
            "Vermerk",
        ),
    )
    for row in accounts:
        table.add(
            row.pk, row.performance_id, row.fee, row.travel, row.extras, row.invoice_id, row.note
        )
    claims = MusicianClaim.objects.filter(
        organization=org, assignment__performance__event__starts_at__date__range=(start, end)
    )
    fees = Table(
        "musikerverguetungen.csv",
        "Musikervergütungen",
        "Freigaben und Bestandteile in EUR",
        _columns(
            "Kennung",
            "Einteilung",
            "Gage",
            "Pauschale",
            "Auslagen",
            "Teilnahme",
            "Status",
            "Freigegeben am",
            "Vermerk",
        ),
    )
    for row in claims:
        fees.add(
            row.pk,
            row.assignment_id,
            row.fee,
            row.allowance,
            row.expenses,
            row.attended,
            row.status,
            row.approved_at,
            row.note,
        )
    payments = Table(
        "auftrittsausgaben.csv",
        "Auftrittsausgaben",
        "Zuordnungen einschließlich stornierter Originalbuchungen",
        _columns("Kennung", "Auftrittsabrechnung", "Vergütung", "Buchung"),
    )
    for row in PerformanceExpense.objects.filter(
        organization=org, booking__date__range=(start, end)
    ).select_related("booking"):
        payments.add(row.pk, row.account_id, row.claim_id, row.booking.display_number)
    return [table, fees, payments]
