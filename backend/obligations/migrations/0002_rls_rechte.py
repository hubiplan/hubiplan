"""Fristenkalender: Zeilenschutz je Einheit und Rechte für bestehende Rollen.

Rollen der Einheit, die Einstellungen, Versammlungen oder die Kasse bearbeiten, dürfen den
Fristenkalender pflegen; wer diese Bereiche nur liest oder die Einheit vertritt, darf ihn lesen. Rückweg: Codes entfernen.
"""

from django.db import migrations

from core.rls import ORG, disable_rls_sql, enable_policy_sql

TABLES = ("obligations_obligation", "obligations_obligationdone")
VIEW = "obligations.view"
EDIT = "obligations.edit"
EDITORS = {"settings.edit", "meetings.edit", "finance.edit"}
READERS = {"settings.view", "meetings.view", "finance.view"}


def _bypass(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(enable_policy_sql(table, f"organization_id = {ORG}"))
    # Verlauf und zuständige Rolle gehören zur selben Einheit wie die Pflicht
    schema_editor.execute("""
        CREATE FUNCTION obligation_scope_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE parent_org bigint;
        BEGIN
          IF TG_TABLE_NAME = 'obligations_obligation' THEN
            IF NEW.role_id IS NULL THEN
              RETURN NEW;
            END IF;
            SELECT organization_id INTO parent_org FROM access_role WHERE id = NEW.role_id;
          ELSE
            SELECT organization_id INTO parent_org
              FROM obligations_obligation WHERE id = NEW.obligation_id;
          END IF;
          IF parent_org IS DISTINCT FROM NEW.organization_id THEN
            RAISE EXCEPTION 'obligation scope mismatch' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
    """)
    for table in TABLES:
        schema_editor.execute(f"""CREATE TRIGGER obligation_scope_guard BEFORE INSERT OR UPDATE
            ON {table} FOR EACH ROW EXECUTE FUNCTION obligation_scope_guard()""")


def no_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS obligation_scope_guard ON {table}")
        schema_editor.execute(disable_rls_sql(table))
    schema_editor.execute("DROP FUNCTION IF EXISTS obligation_scope_guard()")


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
        ("obligations", "0001_vereinspflichten"),
        ("access", "0018_geschaeftspartner"),
    ]

    operations = [
        migrations.RunPython(rls, no_rls),
        migrations.RunPython(grant, revoke),
    ]
