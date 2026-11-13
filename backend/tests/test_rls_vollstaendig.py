"""Jede Tabelle mit Vereinsbezug hat Zeilenschutz oder steht hier mit Grund (Gesamtaudit 13.11.,
V-02).

Ohne diesen Wächter fiele nicht auf, wenn ein neues Modul eine Tabelle mit ``organization_id``
anlegt und den Zeilenschutz vergisst; die Trennung der Vereine hinge dort allein am
Anwendungscode.
"""

import pytest
from django.db import connection

pytestmark = pytest.mark.django_db

# Tabellen mit organization_id ohne Zeilenschutz, je mit Grund. Nur mit Begründung erweitern.
OHNE_RLS = {
    "organizations_organization": "die Einheiten selbst (Spalte der übergeordneten Einheit); "
    "Zugriff über die Rechteprüfung",
    "organizations_instanceaddress": "Adresse → Verein wird vor jeder Anmeldung aufgelöst",
    "organizations_imprint": "Impressum, öffentlich und vor der Anmeldung lesbar",
    "organizations_sociallink": "öffentliche Links der Vereinswebseite",
    "portal_loginlink": "Anmeldelink wird ohne Sitzung über seinen Schlüssel gefunden",
    "core_datakey": "Schlüsselverwaltung der Feldverschlüsselung, unterhalb des Zeilenschutzes",
    "core_datakeyrotation": "Schlüsselwechsel, Systemaufgabe über alle Vereine",
    "finance_gobd_freigabe": "Freigaben der Festschreibung; die Rolle der Anwendung hat darauf "
    "keinerlei Rechte (finance 0032), nur die Funktionen der Datenbank",
    "letterhead_letterhead": "Altbestand; der Zugriff läuft über die Rechteprüfung der Ansichten",
}


def _ohne_rls() -> set[str]:
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
            JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'organization_id'
                AND NOT a.attisdropped
            WHERE c.relkind = 'r' AND NOT c.relrowsecurity
            """
        )
        return {row[0] for row in cur.fetchall()}


def test_jede_vereinstabelle_hat_zeilenschutz():
    if connection.vendor != "postgresql":
        pytest.skip("Zeilenschutz gibt es nur unter PostgreSQL")
    assert _ohne_rls() - set(OHNE_RLS) == set()


def test_ausnahmeliste_ist_aktuell():
    """Bekommt eine Tabelle der Liste Zeilenschutz, fliegt sie aus der Liste."""
    if connection.vendor != "postgresql":
        pytest.skip("Zeilenschutz gibt es nur unter PostgreSQL")
    assert set(OHNE_RLS) - _ohne_rls() == set()
