"""Kennungen, Abrufprotokoll und Benachrichtigungen: nur die eigene Einheit sieht sie. Der
Zustelllauf und das Einreihen arbeiten systemweit (``partnerapi/webhooks.py``)."""

from django.db import migrations

from core.rls import ORG, disable_rls_sql, enable_policy_sql

TABLES = ("partnerapi_recordref", "partnerapi_readlog", "partnerapi_webhookdelivery")


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        for table in TABLES:
            schema_editor.execute(enable_policy_sql(table, f"organization_id = {ORG}"))


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        for table in TABLES:
            schema_editor.execute(disable_rls_sql(table))


class Migration(migrations.Migration):
    dependencies = [("partnerapi", "0003_stufe2")]
    operations = [migrations.RunPython(forwards, backwards)]
