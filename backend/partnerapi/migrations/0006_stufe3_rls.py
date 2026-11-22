"""Einträge und Wiederholungsschutz des Schreibens: nur die eigene Einheit sieht sie."""

from django.db import migrations

from core.rls import ORG, disable_rls_sql, enable_policy_sql

TABLES = ("partnerapi_writtenrecord", "partnerapi_idempotencykey")


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        for table in TABLES:
            schema_editor.execute(enable_policy_sql(table, f"organization_id = {ORG}"))


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        for table in TABLES:
            schema_editor.execute(disable_rls_sql(table))


class Migration(migrations.Migration):
    dependencies = [("partnerapi", "0005_stufe3")]
    operations = [migrations.RunPython(forwards, backwards)]
