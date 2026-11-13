"""Zeilenschutz für den Briefbogen (Gesamtaudit 13.11., V-02): bisher hing die Trennung der
Vereine hier allein an der Rechteprüfung der Ansichten."""

from django.db import migrations

from core.rls import disable_rls_sql, enable_rls_sql

TABLE = "letterhead_letterhead"


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(enable_rls_sql(TABLE))


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(disable_rls_sql(TABLE))


class Migration(migrations.Migration):
    dependencies = [("letterhead", "0003_wahl_rls")]
    operations = [migrations.RunPython(forwards, backwards)]
