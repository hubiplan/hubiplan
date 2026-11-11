"""Verbindungen der KI-Assistenten: nur das eigene Konto und die eigene Einheit sehen sie."""

from django.db import migrations

from core.rls import ORG, USER, disable_rls_sql, enable_policy_sql

TABLE = "mcpserver_mcpgrant"


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            enable_policy_sql(TABLE, f"user_id = {USER} OR organization_id = {ORG}")
        )


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(disable_rls_sql(TABLE))


class Migration(migrations.Migration):
    dependencies = [("mcpserver", "0001_anmeldung")]
    operations = [migrations.RunPython(forwards, backwards)]
