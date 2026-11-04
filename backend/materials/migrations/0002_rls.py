from django.db import migrations

from core.rls import ORG, disable_rls_sql, enable_policy_sql

TABLES = ("materialitem", "materialeventlink", "materialtodolink", "materialdocumentlink",
          "materialphoto", "materialrevision")


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    dept = "NULLIF(current_setting('app.todo_department_id', true), '')::bigint"
    for name in TABLES:
        schema_editor.execute(enable_policy_sql(f"materials_{name}",
            f"organization_id = {ORG} AND department_id IS NOT DISTINCT FROM {dept}"))
    schema_editor.execute("""
        CREATE FUNCTION material_scope_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE parent_org bigint; parent_dept bigint; target_org bigint;
        BEGIN
          IF NEW.department_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM organizations_organization WHERE id = NEW.department_id
              AND organization_id = NEW.organization_id AND type = 'unit'
          ) THEN RAISE EXCEPTION 'material department mismatch' USING ERRCODE = '23514'; END IF;
          IF TG_TABLE_NAME <> 'materials_materialitem' THEN
            SELECT organization_id, department_id INTO parent_org, parent_dept
              FROM materials_materialitem WHERE id = NEW.item_id;
            IF parent_org IS NULL OR parent_org <> NEW.organization_id OR
               parent_dept IS DISTINCT FROM NEW.department_id THEN
              RAISE EXCEPTION 'material item scope mismatch' USING ERRCODE = '23514';
            END IF;
          END IF;
          IF TG_TABLE_NAME = 'materials_materialitem' THEN
            IF NEW.member_id IS NULL THEN RETURN NEW; END IF;
            SELECT organization_id INTO target_org FROM members_membership WHERE id = NEW.member_id;
          ELSIF TG_TABLE_NAME = 'materials_materialeventlink' THEN
            IF NEW.event_id IS NULL THEN RETURN NEW; END IF;
            SELECT organization_id INTO target_org FROM events_event WHERE id = NEW.event_id;
          ELSIF TG_TABLE_NAME = 'materials_materialtodolink' THEN
            SELECT organization_id INTO target_org FROM todos_todo WHERE id = NEW.todo_id;
          ELSIF TG_TABLE_NAME = 'materials_materialdocumentlink' THEN
            SELECT organization_id INTO target_org FROM documents_document WHERE id = NEW.document_id;
          ELSE RETURN NEW;
          END IF;
          IF target_org IS NULL OR target_org <> NEW.organization_id THEN
            RAISE EXCEPTION 'material target scope mismatch' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
    """)
    for name in TABLES:
        schema_editor.execute(f"""CREATE TRIGGER material_scope_guard BEFORE INSERT OR UPDATE
            ON materials_{name} FOR EACH ROW EXECUTE FUNCTION material_scope_guard()""")


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for name in TABLES:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS material_scope_guard ON materials_{name}")
        schema_editor.execute(disable_rls_sql(f"materials_{name}"))
    schema_editor.execute("DROP FUNCTION IF EXISTS material_scope_guard()")


class Migration(migrations.Migration):
    dependencies = [("materials", "0001_initial")]
    operations = [migrations.RunPython(forwards, backwards)]
