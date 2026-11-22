"""API-Zugänge: nur die eigene Einheit sieht sie. Die Schlüsselprüfung sucht systemweit über
die Prüfsumme (``partnerapi/auth.py``, Umgehung nur für diese eine Abfrage)."""

from django.db import migrations

from core.rls import ORG, disable_rls_sql, enable_policy_sql

TABLE = "partnerapi_apiaccess"


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(enable_policy_sql(TABLE, f"organization_id = {ORG}"))


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(disable_rls_sql(TABLE))


class Migration(migrations.Migration):
    dependencies = [("partnerapi", "0001_zugaenge")]
    operations = [migrations.RunPython(forwards, backwards)]
