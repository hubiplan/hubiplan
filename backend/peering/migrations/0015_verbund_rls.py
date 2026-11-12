"""Verbundtabellen mit Daten von Partnerinstanzen: Row-Level Security über die Kopplung
(Gesamtaudit 11.11., S-07). Eine Zeile sieht nur die eigene Einheit der Kopplung und deren
Platzhalter der Gegenseite (dort arbeitet niemand). Eingänge laufen im Bereich der
Einheit (peering/services.py, unit_context), Versand und Aufgaben mit Umgehung.

Nicht darunter: ``peering_message`` (Postausgang und Nachweise, Inhalt verschlüsselt und nach
der Zustellung gelöscht; Versand wird aus Abläufen mehrerer Einheiten angestoßen)."""

from django.db import migrations

from core.rls import ORG, disable_rls_sql, enable_policy_sql, enable_rls_sql

COUPLING_TABLES = (
    "peering_remotemember",
    "peering_remoteinvoice",
    "peering_remotetransfer",
    "peering_remotecircular",
    "peering_remotestate",
)
# Eigene Einheit oder ihr Platzhalter der Gegenseite: Pakete wie die Mitgliedermeldung
# arbeiten im Bereich des Platzhalters (peering/packet_members.py, unit_context)
OWN = (
    "coupling_id IN (SELECT id FROM peering_coupling "
    f"WHERE local_unit_id = {ORG} OR remote_unit_id = {ORG})"
)


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in COUPLING_TABLES:
        schema_editor.execute(enable_policy_sql(table, OWN))
    schema_editor.execute(enable_rls_sql("peering_spinoff"))


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in (*COUPLING_TABLES, "peering_spinoff"):
        schema_editor.execute(disable_rls_sql(table))


class Migration(migrations.Migration):
    dependencies = [("peering", "0014_reception_budget")]
    operations = [migrations.RunPython(forwards, backwards)]
