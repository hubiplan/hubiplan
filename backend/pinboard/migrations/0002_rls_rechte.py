"""Pinnwand: Zeilenschutz je Einheit und Rechte für bestehende Rollen.

Rollen des Vereins und der Untereinheiten, die Rundschreiben oder Termine bearbeiten, dürfen
die Pinnwand beschreiben; wer Rundschreiben sehen darf, sieht sie auch in der Verwaltung.
Rückweg: Codes entfernen, Zeilenschutz aus.
"""

from django.db import migrations

from core.rls import ORG, disable_rls_sql, enable_policy_sql

TABLES = ("pinboard_notice", "pinboard_noticephoto", "pinboard_noticeseen")
VIEW = "pinboard.view"
EDIT = "pinboard.edit"
EDITORS = {"circulars.edit", "events.edit"}
VIEWERS = {"circulars.view"}


def _bypass(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(enable_policy_sql(table, f"organization_id = {ORG}"))
    # Fotos gehören zur Organisation ihres Beitrags, gelesen zur Organisation der Mitgliedschaft,
    # die Untereinheit zur Organisation des Beitrags
    schema_editor.execute("""
        CREATE FUNCTION pinboard_scope_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE parent_org bigint;
        BEGIN
          IF TG_TABLE_NAME = 'pinboard_notice' THEN
            IF NEW.department_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM organizations_organization
                 WHERE id = NEW.department_id AND type = 'unit'
                   AND organization_id = NEW.organization_id) THEN
              RAISE EXCEPTION 'pinboard scope mismatch' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
          ELSIF TG_TABLE_NAME = 'pinboard_noticephoto' THEN
            SELECT organization_id INTO parent_org FROM pinboard_notice WHERE id = NEW.notice_id;
          ELSE
            SELECT organization_id INTO parent_org
              FROM members_membership WHERE id = NEW.membership_id;
          END IF;
          IF parent_org IS DISTINCT FROM NEW.organization_id THEN
            RAISE EXCEPTION 'pinboard scope mismatch' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
    """)
    for table in TABLES:
        schema_editor.execute(f"""CREATE TRIGGER pinboard_scope_guard BEFORE INSERT OR UPDATE
            ON {table} FOR EACH ROW EXECUTE FUNCTION pinboard_scope_guard()""")


def no_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS pinboard_scope_guard ON {table}")
        schema_editor.execute(disable_rls_sql(table))
    schema_editor.execute("DROP FUNCTION IF EXISTS pinboard_scope_guard()")


def grant(apps, schema_editor):
    _bypass(schema_editor)
    Role = apps.get_model("access", "Role")
    rows = Role._base_manager.filter(organization__type="club")
    for role in rows.iterator():
        perms = set(role.permissions or [])
        add = set()
        if perms & EDITORS:
            add = {VIEW, EDIT}
        elif perms & VIEWERS:
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
        ("pinboard", "0001_pinnwand"),
        ("access", "0018_geschaeftspartner"),
    ]

    operations = [
        migrations.RunPython(rls, no_rls),
        migrations.RunPython(grant, revoke),
    ]
