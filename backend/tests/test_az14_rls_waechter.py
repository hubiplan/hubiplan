"""Wächter für den Zeilenschutz über alle Verweise auf Einheiten und Konten (Gesamtaudit
15.11., AZ-14).

Der Wächter in ``test_rls_vollstaendig`` erkennt nur Spalten namens ``organization_id``.
Tabellen mit ``unit_id``, ``local_unit_id`` oder nur ``user_id`` fielen durch. Dieser
Wächter liest die Fremdschlüssel aus ``pg_constraint``: Jede Tabelle mit einem Verweis auf
eine Einheit hat Zeilenschutz oder steht mit Grund in der Liste. Ebenso jede Tabelle, die
nur auf ein Konto verweist (ohne Einheit). Nur mit Begründung erweitern.
"""

import pytest
from django.db import connection

from .test_rls_vollstaendig import OHNE_RLS as OHNE_RLS_ORGANISATION

pytestmark = pytest.mark.django_db

# Verweis auf eine Einheit über eine andere Spalte als organization_id, ohne Zeilenschutz
OHNE_RLS_EINHEIT = {
    **OHNE_RLS_ORGANISATION,
    "peering_coupling": "Kopplungen; jeder Zugriff filtert nach der eigenen Einheit "
    "(peering/api.py, local_unit), der Eingang sucht systemweit über die Gegenstelle",
    "peering_couplingcode": "Kopplungscodes; Abruf nur über den Code selbst bzw. die Einheit",
}

# Verweis nur auf ein Konto (ohne Einheit), ohne Zeilenschutz
OHNE_RLS_KONTO = {
    "accounts_emailchange": "E-Mail-Wechsel des eigenen Kontos; Zugriff nur über das "
    "angemeldete Konto bzw. den Bestätigungsschlüssel",
    "changes_requestkey": "Wiederholschutz je Konto (Idempotency-Key)",
    "devices_device": "Geräte des eigenen Kontos; Zugriff nur über das angemeldete Konto",
    "devices_pairingcode": "Verbindungscodes der App; eingelöst über den Code",
    "mcpserver_mcpclient": "KI-Verbindungen; Zugriff über das Konto bzw. den Zugangsschlüssel",
    "peering_remoteaccount": "ferne Konten im Verbund; Zuordnung bei der Anmeldung (peering/sso)",
    "peering_loginlink": "Anmeldelinks im Verbund; gefunden über ihren Schlüssel vor der Anmeldung",
    "account_emailaddress": "allauth: Adressen des eigenen Kontos (Kontoverwaltung über allauth "
    "gesperrt, config/urls.py)",
    "mfa_authenticator": "allauth: zweite Faktoren des eigenen Kontos; nur über die Anmeldung",
    "accounts_user_groups": "Django-Gruppen; von HUBIplan nicht genutzt",
    "accounts_user_user_permissions": "Django-Rechte; von HUBIplan nicht genutzt",
    "django_admin_log": "Protokoll des Django-Admins (standardmäßig aus, nur Superuser mit 2FA)",
    "circulars_mailinglist_senders": "Zwischentabelle Verteiler ↔ Absender; Zugriff nur über "
    "den Verteiler der Einheit, der Zeilenschutz hat",
}

FREMDSCHLUESSEL = """
    SELECT DISTINCT c.relname
    FROM pg_constraint k
    JOIN pg_class c ON c.oid = k.conrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
    JOIN pg_class ziel ON ziel.oid = k.confrelid
    WHERE k.contype = 'f' AND ziel.relname = %s AND c.relkind = 'r' AND NOT c.relrowsecurity
"""


def _ohne_rls_mit_verweis(ziel: str) -> set[str]:
    with connection.cursor() as cur:
        cur.execute(FREMDSCHLUESSEL, [ziel])
        return {row[0] for row in cur.fetchall()}


@pytest.fixture(autouse=True)
def nur_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("Zeilenschutz gibt es nur unter PostgreSQL")


def test_jede_tabelle_mit_verweis_auf_eine_einheit_hat_zeilenschutz():
    missing = _ohne_rls_mit_verweis("organizations_organization") - set(OHNE_RLS_EINHEIT)
    assert missing == set(), sorted(missing)


def test_jede_tabelle_nur_mit_konto_hat_zeilenschutz():
    einheit = _ohne_rls_mit_verweis("organizations_organization")
    missing = _ohne_rls_mit_verweis("accounts_user") - einheit - set(OHNE_RLS_KONTO)
    assert missing == set(), sorted(missing)


def test_ausnahmelisten_sind_aktuell():
    """Bekommt eine Tabelle Zeilenschutz oder verschwindet sie, fliegt sie aus der Liste."""
    einheit = _ohne_rls_mit_verweis("organizations_organization")
    konto = _ohne_rls_mit_verweis("accounts_user")
    veraltet = set(OHNE_RLS_EINHEIT) - einheit - set(OHNE_RLS_ORGANISATION)
    assert veraltet == set(), sorted(veraltet)
    veraltet = set(OHNE_RLS_KONTO) - konto
    assert veraltet == set(), sorted(veraltet)
