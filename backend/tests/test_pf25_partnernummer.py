"""Partnernummer je Einheit eindeutig (Gesamtaudit 15.11., PF-25). Erfundene Daten.

Gleichzeitige Anlagen konnten dieselbe Nummer bekommen. Jetzt sperrt die Vergabe die Einheit,
und die Datenbank weist doppelte Nummern ab. Bestehende Doppelte löst die Migration auf: Der
ältere Partner behält seine Nummer, jede Umnummerierung steht im Änderungsprotokoll.
"""

import pytest
from django.db import IntegrityError, connection, transaction

from audit.models import AuditEntry
from billing.models import BusinessPartner
from billing.partners import resolve_duplicate_numbers
from core.tenancy import rls_bypass

pytestmark = pytest.mark.django_db


def _partner(org, name, number):
    return BusinessPartner.objects.create(organization=org, name=name, number=number)


def test_doppelte_nummer_abgewiesen(orgs):
    with rls_bypass():
        _partner(orgs["a"], "Getränke Beispiel GmbH", "GP-0001")
        _partner(orgs["b"], "Anderer Verein, gleiche Nummer", "GP-0001")  # andere Einheit: ok
        _partner(orgs["a"], "Ohne Nummer 1", "")
        _partner(orgs["a"], "Ohne Nummer 2", "")  # leer bleibt erlaubt
        with pytest.raises(IntegrityError), transaction.atomic():
            _partner(orgs["a"], "Bäckerei Muster", "GP-0001")


def test_bestand_wird_aufgeloest(orgs):
    with rls_bypass(), transaction.atomic():
        with connection.cursor() as cur:
            # Eindeutigkeit mit Bedingung ist in PostgreSQL ein eindeutiger Index
            cur.execute("DROP INDEX partner_nummer_eindeutig")
        alt = _partner(orgs["a"], "Getränke Beispiel GmbH", "GP-0003")
        neu = _partner(orgs["a"], "Bäckerei Muster", "GP-0003")
        _partner(orgs["a"], "Druckerei Beispiel", "GP-0007")
        assert resolve_duplicate_numbers() == 1
        alt.refresh_from_db()
        neu.refresh_from_db()
        assert alt.number == "GP-0003" and neu.number == "GP-0008"
        entry = (
            AuditEntry.objects.filter(organization=orgs["a"], object_id=str(neu.pk))
            .order_by("-id")
            .first()
        )
        assert entry is not None and "GP-0008" in str(entry.changes)
        transaction.set_rollback(True)
