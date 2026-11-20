"""Datenschutz-Werkzeuge: Zeilenschutz je Einheit und Rechte für bestehende Rollen.

Rollen der Einheit, die die Einstellungen bearbeiten, dürfen die Datenschutz-Werkzeuge
pflegen; wer die Einstellungen nur liest oder die Einheit vertritt, darf sie lesen.
Rückweg: Zeilenschutz aufheben und Codes entfernen.
"""

from django.db import migrations

from core.rls import ORG, disable_rls_sql, enable_policy_sql

TABLES = ("privacy_privacysettings", "privacy_processingactivity", "privacy_databreach")
VIEW = "privacy.view"
EDIT = "privacy.edit"
EDITORS = {"settings.edit"}
READERS = {"settings.view"}


def _bypass(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(enable_policy_sql(table, f"organization_id = {ORG}"))


def no_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(disable_rls_sql(table))


def grant(apps, schema_editor):
    _bypass(schema_editor)
    Role = apps.get_model("access", "Role")
    rows = Role._base_manager.filter(
        department__isnull=True, organization__type__in=["club", "federation"]
    )
    for role in rows.iterator():
        perms = set(role.permissions or [])
        add = set()
        if perms & EDITORS:
            add = {VIEW, EDIT}
        elif perms & READERS or getattr(role, "represents", False):
            add = {VIEW}
        if add - perms:
            Role._base_manager.filter(pk=role.pk).update(permissions=sorted(perms | add))


def revoke(apps, schema_editor):
    _bypass(schema_editor)
    Role = apps.get_model("access", "Role")
    for role in Role._base_manager.iterator():
        perms = [p for p in role.permissions or [] if p not in (VIEW, EDIT)]
        if perms != list(role.permissions or []):
            Role._base_manager.filter(pk=role.pk).update(permissions=perms)


class Migration(migrations.Migration):
    dependencies = [
        ("privacy", "0001_datenschutz"),
        ("access", "0018_geschaeftspartner"),
    ]

    operations = [
        migrations.RunPython(rls, no_rls),
        migrations.RunPython(grant, revoke),
    ]
