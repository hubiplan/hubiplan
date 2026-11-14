"""Umfragen: Zeilenschutz je Einheit und Rechte für bestehende Rollen.

Rollen des Vereins und der Untereinheiten, die Termine, Rundschreiben oder Versammlungen
bearbeiten, dürfen Umfragen anlegen und sehen (Fachfrage UM-2). Rückweg: Codes entfernen.
"""

from django.db import migrations

from core.rls import ORG, disable_rls_sql, enable_policy_sql

TABLES = (
    "surveys_survey",
    "surveys_surveyquestion",
    "surveys_surveyoption",
    "surveys_surveyparticipation",
    "surveys_surveyanswer",
)
VIEW = "surveys.view"
EDIT = "surveys.edit"
EDITORS = {"events.edit", "circulars.edit", "meetings.edit"}


def _bypass(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(enable_policy_sql(table, f"organization_id = {ORG}"))
    # Jede Zeile gehört zur selben Organisation wie ihre Umfrage; Termin und Untereinheit
    # zur Organisation der Umfrage
    schema_editor.execute("""
        CREATE FUNCTION survey_scope_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE parent_org bigint;
        BEGIN
          IF TG_TABLE_NAME = 'surveys_survey' THEN
            IF NEW.event_id IS NOT NULL THEN
              SELECT organization_id INTO parent_org FROM events_event WHERE id = NEW.event_id;
              IF parent_org IS DISTINCT FROM NEW.organization_id THEN
                RAISE EXCEPTION 'survey scope mismatch' USING ERRCODE = '23514';
              END IF;
            END IF;
            IF NEW.follow_event_id IS NOT NULL THEN
              SELECT organization_id INTO parent_org
                FROM events_event WHERE id = NEW.follow_event_id;
              IF parent_org IS DISTINCT FROM NEW.organization_id THEN
                RAISE EXCEPTION 'survey scope mismatch' USING ERRCODE = '23514';
              END IF;
            END IF;
            -- Untereinheiten sind Organisationen vom Typ „unit“ (seit organizations 0014)
            IF NEW.department_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM organizations_organization
                 WHERE id = NEW.department_id AND type = 'unit'
                   AND organization_id = NEW.organization_id) THEN
              RAISE EXCEPTION 'survey scope mismatch' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
          ELSIF TG_TABLE_NAME = 'surveys_surveyoption' THEN
            SELECT organization_id INTO parent_org
              FROM surveys_surveyquestion WHERE id = NEW.question_id;
          ELSE
            SELECT organization_id INTO parent_org FROM surveys_survey WHERE id = NEW.survey_id;
          END IF;
          IF parent_org IS DISTINCT FROM NEW.organization_id THEN
            RAISE EXCEPTION 'survey scope mismatch' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
    """)
    for table in TABLES:
        schema_editor.execute(f"""CREATE TRIGGER survey_scope_guard BEFORE INSERT OR UPDATE
            ON {table} FOR EACH ROW EXECUTE FUNCTION survey_scope_guard()""")


def no_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS survey_scope_guard ON {table}")
        schema_editor.execute(disable_rls_sql(table))
    schema_editor.execute("DROP FUNCTION IF EXISTS survey_scope_guard()")


def grant(apps, schema_editor):
    _bypass(schema_editor)
    Role = apps.get_model("access", "Role")
    rows = Role._base_manager.filter(organization__type="club")
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
        ("surveys", "0001_umfragen"),
        ("access", "0018_geschaeftspartner"),
    ]

    operations = [
        migrations.RunPython(rls, no_rls),
        migrations.RunPython(grant, revoke),
    ]
