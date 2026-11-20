"""Glückwünsche: Zeilenschutz je Verein. Rückweg: Zeilenschutz wieder aufheben."""

from django.db import migrations

from core.rls import disable_rls_sql, enable_rls_sql

TABLES = ("greetings_greetingsettings", "greetings_greetingbatch")


def rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(enable_rls_sql(table))


def no_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(disable_rls_sql(table))


class Migration(migrations.Migration):
    dependencies = [("greetings", "0001_glueckwuensche")]

    operations = [migrations.RunPython(rls, no_rls)]
