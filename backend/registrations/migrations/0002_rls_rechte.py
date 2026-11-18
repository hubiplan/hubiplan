"""Anmeldungen: Zeilenschutz je Einheit und Rechte für bestehende Rollen.

Rollen, die Termine bearbeiten, dürfen Anmeldungen sehen und verwalten (Preise zusätzlich nur
mit dem Recht, Rechnungen zu bearbeiten). Rückweg: Codes entfernen, Schutz aufheben.
"""

from django.db import migrations

from core.rls import ORG, disable_rls_sql, enable_policy_sql

TABLES = (
    "registrations_registrationsetup",
    "registrations_priceoption",
    "registrations_pricestep",
    "registrations_registration",
    "registrations_participant",
)
VIEW = "registrations.view"
EDIT = "registrations.edit"
EDITORS = {"events.edit"}
PARENTS = {
    "registrations_registrationsetup": ("events_event", "event_id"),
    "registrations_priceoption": ("registrations_registrationsetup", "setup_id"),
    "registrations_pricestep": ("registrations_priceoption", "price_id"),
    "registrations_registration": ("registrations_registrationsetup", "setup_id"),
    "registrations_participant": ("registrations_registration", "registration_id"),
}


def _bypass(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(enable_policy_sql(table, f"organization_id = {ORG}"))
    branches = []
    for table, (parent, column) in PARENTS.items():
        branches.append(f"""
          {"IF" if not branches else "ELSIF"} TG_TABLE_NAME = '{table}' THEN
            SELECT organization_id INTO parent_org FROM {parent} WHERE id = NEW.{column};""")
    schema_editor.execute(f"""
        CREATE FUNCTION registration_scope_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE parent_org bigint;
        BEGIN
          {"".join(branches)}
          END IF;
          IF parent_org IS DISTINCT FROM NEW.organization_id THEN
            RAISE EXCEPTION 'registration scope mismatch' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
    """)
    for table in TABLES:
        schema_editor.execute(f"""CREATE TRIGGER registration_scope_guard BEFORE INSERT OR UPDATE
            ON {table} FOR EACH ROW EXECUTE FUNCTION registration_scope_guard()""")


def no_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS registration_scope_guard ON {table}")
        schema_editor.execute(disable_rls_sql(table))
    schema_editor.execute("DROP FUNCTION IF EXISTS registration_scope_guard()")


def grant(apps, schema_editor):
    _bypass(schema_editor)
    Role = apps.get_model("access", "Role")
    rows = Role._base_manager.filter(organization__type__in=["club", "federation"])
    for role in rows.iterator():
        perms = set(role.permissions or [])
        if perms & EDITORS and {VIEW, EDIT} - perms:
            Role._base_manager.filter(pk=role.pk).update(permissions=sorted(perms | {VIEW, EDIT}))


def revoke(apps, schema_editor):
    _bypass(schema_editor)
    Role = apps.get_model("access", "Role")
    for role in Role._base_manager.iterator():
        perms = [p for p in role.permissions or [] if p not in (VIEW, EDIT)]
        if perms != list(role.permissions or []):
            Role._base_manager.filter(pk=role.pk).update(permissions=perms)


class Migration(migrations.Migration):
    dependencies = [
        ("registrations", "0001_anmeldungen"),
        ("access", "0018_geschaeftspartner"),
    ]

    operations = [
        migrations.RunPython(rls, no_rls),
        migrations.RunPython(grant, revoke),
    ]
