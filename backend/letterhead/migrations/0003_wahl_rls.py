"""Wahlen für die Briefvorlage: nur das eigene Konto sieht und ändert seine Zeilen (GA8-06/RLS)."""

from django.db import migrations

from core.rls import USER, disable_rls_sql, enable_policy_sql

TABLE = "letterhead_letterheadchoice"


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(enable_policy_sql(TABLE, f"user_id = {USER}"))


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(disable_rls_sql(TABLE))


class Migration(migrations.Migration):
    dependencies = [("letterhead", "0002_zusatzzeile_ohne_doppeltes_jahr")]
    operations = [migrations.RunPython(forwards, backwards)]
