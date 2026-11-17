"""UMSATZSTEUER-PROBE zu Gesamtaudit 15.11., AZ-04 (erfundene Daten).

Prüft unter der Rolle der Anwendung (Zeilenschutz wie im Betrieb), ob die Umsätze einer
Untereinheit mit eigener Kasse in der Umsatzsteuer-Voranmeldung des Vereins mitzählen
(``finance/vat.py``: ``_bookings`` liest ``organization__in=orgs`` im Kontext des Vereins).
Schlägt dieser Test fehl, liest ``vat.py`` die Untereinheiten wie ``tax._totals_of`` je in
ihrem eigenen Bereich."""
# ruff: noqa: F811

import pytest

from organizations.models import Department

from .test_umsatzsteuer import Kasse, c, club, get, lines  # noqa: F401

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("anfragen_unter_app_rolle")]


def test_ust_probe_untereinheit_zaehlt_in_voranmeldung_des_vereins(c, club):
    """UMSATZSTEUER-PROBE (AZ-04): Umsatz und Vorsteuer der Untereinheit mit eigener Kasse
    zählen in der Voranmeldung des Vereins mit."""
    unit = Department.objects.create(
        organization=club, name="Spielmannszug", founding_year=1980, own_workspace=True
    )
    unit.enabled_modules = sorted({*(unit.enabled_modules or []), "finance", "tax"})
    unit.tax_areas_enabled = True
    unit.save()
    Kasse(club).buchen("business", "119.00", "19")
    sub = Kasse(unit)
    sub.buchen("business", "238.00", "19")
    sub.buchen("business", "119.00", "19", kind="expense")

    data = get(c, club, art="quarter", zeitraum=1)
    by = lines(data)
    # 100 € netto im Verein + 200 € netto in der Untereinheit
    assert by["81"]["base"] == "300.00" and by["81"]["tax"] == "57.00"
    # Vorsteuer nur aus der Ausgabe der Untereinheit
    assert by["66"]["tax"] == "19.00"
    assert by["83"]["tax"] == "38.00"
