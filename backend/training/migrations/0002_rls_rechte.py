"""Training: Zeilenschutz je Verein und Rechte für bestehende Rollen.

Rollen des Vereins und der Untereinheiten, die Termine bearbeiten, dürfen Trainings anlegen und
die Anwesenheit erfassen; wer Termine sehen darf, sieht auch die Trainings.
Rückweg: Codes entfernen, Zeilenschutz aus.
"""

from django.db import migrations

from core.rls import ORG, disable_rls_sql, enable_policy_sql

TABLES = ("training_trainingsession", "training_attendance", "training_shootingentry")
VIEW = "training.view"
EDIT = "training.edit"
EDITORS = {"events.edit"}
VIEWERS = {"events.view"}


def _bypass(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(enable_policy_sql(table, f"organization_id = {ORG}"))
    # Termin und Untereinheit gehören zum Verein des Trainings, Anwesenheit und Schießbuch zum
    # Verein ihrer Mitgliedschaft und ihres Trainings
    schema_editor.execute("""
        CREATE FUNCTION training_scope_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE parent_org bigint;
        BEGIN
          IF TG_TABLE_NAME = 'training_trainingsession' THEN
            IF NEW.event_id IS NOT NULL THEN
              SELECT organization_id INTO parent_org FROM events_event WHERE id = NEW.event_id;
              IF parent_org IS DISTINCT FROM NEW.organization_id THEN
                RAISE EXCEPTION 'training scope mismatch' USING ERRCODE = '23514';
              END IF;
            END IF;
            IF NEW.department_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM organizations_organization
                 WHERE id = NEW.department_id AND type = 'unit'
                   AND organization_id = NEW.organization_id) THEN
              RAISE EXCEPTION 'training scope mismatch' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
          END IF;
          SELECT organization_id INTO parent_org
            FROM members_membership WHERE id = NEW.membership_id;
          IF parent_org IS DISTINCT FROM NEW.organization_id THEN
            RAISE EXCEPTION 'training scope mismatch' USING ERRCODE = '23514';
          END IF;
          IF TG_TABLE_NAME = 'training_attendance' THEN
            SELECT organization_id INTO parent_org
              FROM training_trainingsession WHERE id = NEW.session_id;
          ELSIF NEW.attendance_id IS NOT NULL THEN
            SELECT organization_id INTO parent_org
              FROM training_attendance WHERE id = NEW.attendance_id;
          END IF;
          IF parent_org IS DISTINCT FROM NEW.organization_id THEN
            RAISE EXCEPTION 'training scope mismatch' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
    """)
    for table in TABLES:
        schema_editor.execute(f"""CREATE TRIGGER training_scope_guard BEFORE INSERT OR UPDATE
            ON {table} FOR EACH ROW EXECUTE FUNCTION training_scope_guard()""")


def no_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS training_scope_guard ON {table}")
        schema_editor.execute(disable_rls_sql(table))
    schema_editor.execute("DROP FUNCTION IF EXISTS training_scope_guard()")


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
        ("training", "0001_training_anwesenheit"),
        ("access", "0018_geschaeftspartner"),
    ]

    operations = [
        migrations.RunPython(rls, no_rls),
        migrations.RunPython(grant, revoke),
    ]
