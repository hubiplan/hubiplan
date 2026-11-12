"""Verbundtabellen mit Daten von Partnerinstanzen: Row-Level Security über die Kopplung
(Gesamtaudit 11.11., S-07). Eine Zeile sieht nur die eigene Einheit der Kopplung; Empfang
und Versand im Verbund laufen wie bisher mit Umgehung (peering/server.py, peering/tasks.py).

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
OWN = f"coupling_id IN (SELECT id FROM peering_coupling WHERE local_unit_id = {ORG})"


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
