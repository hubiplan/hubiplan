from importlib import import_module

from django.db import migrations

from core.rls import APP_ROLE, BYPASS, ORG, USER, enable_policy_sql, enable_rls_sql

DEPT = "NULLIF(current_setting('app.todo_department_id', true), '')::bigint"
PREVIEW = "NULLIF(current_setting('app.todo_role_id', true), '')::bigint"
SOURCE = "NULLIF(current_setting('app.todo_source_id', true), '')::bigint"


def assigned(role="a.role_id"):
    return f"""EXISTS (SELECT 1 FROM access_roleassignment a
        WHERE a.role_id = {role} AND a.valid_from <= CURRENT_DATE
        AND (a.valid_until IS NULL OR a.valid_until >= CURRENT_DATE)
        AND (a.user_id = {USER} OR EXISTS (SELECT 1 FROM portal_portalaccess p
            WHERE p.membership_id = a.membership_id AND p.user_id = {USER})))"""


def scope_access(edit=False):
    permissions = "r.permissions ? 'todos.edit'" if edit else "(r.permissions ? 'todos.view' OR r.permissions ? 'todos.edit')"
    return f"""EXISTS (SELECT 1 FROM access_role r
        WHERE r.organization_id = {ORG}
        AND {permissions}
        AND (({DEPT} IS NULL AND r.department_id IS NULL)
             OR r.department_id IN (WITH RECURSIVE units AS (
                SELECT id, parent_id FROM organizations_organization WHERE id = {DEPT}
                UNION ALL SELECT o.id, o.parent_id FROM organizations_organization o
                JOIN units u ON o.id = u.parent_id WHERE o.type = 'unit'
             ) SELECT id FROM units)) AND {assigned('r.id')})"""


def recipient(alias="s", edit=False):
    role = f"{alias}.role_id"
    preview = "" if edit else f" OR {role} = {PREVIEW}"
    return f"({alias}.user_id = {USER} OR {assigned(role)}{preview})"


def grant(edit=False):
    level = "AND s.level = 'edit'" if edit else ""
    return f"""EXISTS (SELECT 1 FROM todos_todoshare s WHERE s.todo_id = todos_todo.id
        AND s.target_org_id = {ORG}
        AND s.target_department_id IS NOT DISTINCT FROM {DEPT}
        {level} AND {recipient(edit=edit)})"""


def policies(schema_editor, table, read, write, delete=None):
    schema_editor.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY; DROP POLICY IF EXISTS tenant_isolation ON {table};')
    for name, operation, expression in [("task_read", "SELECT", read), ("task_insert", "INSERT", write), ("task_update", "UPDATE", write), ("task_delete", "DELETE", delete or write)]:
        schema_editor.execute(f'DROP POLICY IF EXISTS {name} ON {table}')
        rule = f"(({expression}) OR {BYPASS})"
        clause = f"WITH CHECK ({rule})" if operation == "INSERT" else f"USING ({rule})"
        if operation == "UPDATE":
            clause += f" WITH CHECK ({rule})"
        schema_editor.execute(f'CREATE POLICY {name} ON {table} FOR {operation} {clause}')


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    local = f"organization_id = {ORG} AND department_id IS NOT DISTINCT FROM {DEPT}"
    own = f"(created_by_id = {USER} OR owner_id = {USER}) AND {PREVIEW} IS NULL"
    shared = f"shared AND (NOT per_unit OR ({local}))"
    access = scope_access()
    read = f"({access} AND ((({local}) AND {own}) OR ({shared} AND {grant()}))) OR ({ORG} IS NULL AND {own} AND NOT shared) OR id = {SOURCE}"
    write = f"{PREVIEW} IS NULL AND {access} AND ((({local}) AND owner_id = {USER}) OR ({shared} AND {grant(True)}))"
    delete = f"{PREVIEW} IS NULL AND {access} AND ({local}) AND owner_id = {USER}"
    policies(schema_editor, "todos_todo", read, write, delete)
    share_read = f"organization_id = {ORG} OR (target_org_id = {ORG} AND target_department_id IS NOT DISTINCT FROM {DEPT} AND {recipient('todos_todoshare')})"
    same = "target_org_id = t.organization_id AND target_department_id IS NOT DISTINCT FROM t.department_id"
    graph = f"""({same}) OR (NOT t.distributed AND (
        (t.department_id IS NOT NULL AND target_org_id = t.organization_id AND target_department_id IS NULL)
        OR (t.department_id IS NULL AND EXISTS (SELECT 1 FROM organizations_organization src,
            organizations_organization dst WHERE src.id = t.organization_id AND dst.id = target_org_id
            AND src.is_active AND dst.is_active AND (
                (src.type = 'platform' AND dst.type IN ('federation', 'club') AND target_department_id IS NULL)
                OR (src.type = 'federation' AND dst.type = 'club' AND dst.parent_id = src.id AND target_department_id IS NULL)
                OR (src.type = 'club' AND dst.type = 'federation' AND src.parent_id = dst.id AND target_department_id IS NULL)
                OR (src.type = 'club' AND dst.id = src.id AND EXISTS (SELECT 1 FROM organizations_organization dep WHERE dep.id = target_department_id AND dep.organization_id = src.id AND dep.type = 'unit' AND dep.is_active))
            )))
        ))"""
    # Nur eine Ja/Nein-Prüfung über Besitz-/Beziehungsdaten. Der feste Suchpfad und
    # die begrenzte Rückgabe vermeiden sowohl RLS-Rekursion als auch Inhaltszugriff.
    target_graph = graph.replace("target_org_id", "p_org").replace("target_department_id", "p_dept")
    schema_editor.execute(f"""
        CREATE OR REPLACE FUNCTION todos_share_target_allowed(p_todo bigint, p_org bigint, p_dept bigint)
        RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
            SELECT EXISTS (SELECT 1 FROM public.todos_todo t WHERE t.id = p_todo
                AND t.owner_id = {USER} AND t.organization_id = {ORG} AND ({target_graph}));
        $$;
        REVOKE ALL ON FUNCTION todos_share_target_allowed(bigint, bigint, bigint) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION todos_share_target_allowed(bigint, bigint, bigint) TO {APP_ROLE};
    """)
    share_write = f"{PREVIEW} IS NULL AND {scope_access(True)} AND organization_id = {ORG} AND todos_share_target_allowed(todo_id, target_org_id, target_department_id)"
    policies(schema_editor, "todos_todoshare", share_read, share_write)
    parent = "EXISTS (SELECT 1 FROM todos_todo t WHERE t.id = todo_id AND t.organization_id = todos_todoattachment.organization_id)"
    edit_parent = f"EXISTS (SELECT 1 FROM todos_todo WHERE id = todo_id AND (({local} AND owner_id = {USER}) OR ({shared} AND {grant(True)})))"
    policies(schema_editor, "todos_todoattachment", parent, f"{PREVIEW} IS NULL AND {parent} AND {edit_parent}")
    progress_read = "EXISTS (SELECT 1 FROM todos_todo t WHERE t.id = source_id AND t.organization_id = todos_todoprogress.organization_id)"
    policies(schema_editor, "todos_todoprogress", progress_read, "false")
    # Vorlagentexte bleiben beim verantwortlichen Konto. Andere Beteiligte erhalten
    # ausschließlich die nach aktueller Aufgabenprüfung projizierten Regelmetadaten.
    series_own = f"{local} AND owner_id = {USER} AND {PREVIEW} IS NULL AND {access}"
    personal = f"{ORG} IS NULL AND owner_id = {USER} AND EXISTS (SELECT 1 FROM todos_todo t WHERE t.series_id = todos_todoseries.id AND NOT t.shared)"
    policies(schema_editor, "todos_todoseries", f"({series_own}) OR ({personal})", series_own)
    # Einzeln geprüfte Aufgabenrücknahmen öffnen nur ihr Paket und das neue eigene Paket.
    old = "NULLIF(current_setting('app.todo_undo_id', true), '')::uuid"
    new = "NULLIF(current_setting('app.todo_change_id', true), '')::uuid"
    for table, key in [("changes_changeset", "id"), ("changes_changerecord", "change_set_id")]:
        token = f"{key} IN ({old}, {new})"
        if table == "changes_changerecord":
            token = f"({token}) AND model = 'todos.todo'"
        schema_editor.execute(enable_policy_sql(table, f"organization_id = {ORG} OR ({token})"))
    schema_editor.execute(f"""
        CREATE OR REPLACE FUNCTION todos_immutable_scope() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF {BYPASS} THEN RETURN NEW; END IF;
            IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
               OR NEW.department_id IS DISTINCT FROM OLD.department_id
               OR NEW.origin_id IS DISTINCT FROM OLD.origin_id
               OR NEW.distributed IS DISTINCT FROM OLD.distributed
               OR NEW.series_id IS DISTINCT FROM OLD.series_id
               OR NEW.sequence_no IS DISTINCT FROM OLD.sequence_no THEN
                RAISE EXCEPTION 'immutable task scope';
            END IF;
            IF OLD.distributed AND (NEW.title IS DISTINCT FROM OLD.title
               OR NEW.description IS DISTINCT FROM OLD.description
               OR NEW.due_date IS DISTINCT FROM OLD.due_date
               OR NEW.due_time IS DISTINCT FROM OLD.due_time
               OR NEW.timezone IS DISTINCT FROM OLD.timezone
               OR NEW.central_attachment_ids IS DISTINCT FROM OLD.central_attachment_ids) THEN
                RAISE EXCEPTION 'immutable central task fields';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER todo_immutable_scope BEFORE UPDATE ON todos_todo
            FOR EACH ROW EXECUTE FUNCTION todos_immutable_scope();
        CREATE OR REPLACE FUNCTION todos_attachment_scope() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF {BYPASS} THEN RETURN NEW; END IF;
            IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
               OR NEW.department_id IS DISTINCT FROM OLD.department_id
               OR NEW.todo_id IS DISTINCT FROM OLD.todo_id THEN
                RAISE EXCEPTION 'immutable attachment scope';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER todo_attachment_scope BEFORE UPDATE ON todos_todoattachment
            FOR EACH ROW EXECUTE FUNCTION todos_attachment_scope();
    """)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP TRIGGER IF EXISTS todo_immutable_scope ON todos_todo; DROP FUNCTION IF EXISTS todos_immutable_scope(); DROP TRIGGER IF EXISTS todo_attachment_scope ON todos_todoattachment; DROP FUNCTION IF EXISTS todos_attachment_scope();")
    for table in ("todos_todo", "todos_todoshare", "todos_todoattachment", "todos_todoprogress", "todos_todoseries"):
        for name in ("task_read", "task_insert", "task_update", "task_delete"):
            schema_editor.execute(f"DROP POLICY IF EXISTS {name} ON {table}")
    import_module("todos.migrations.0004_freigaben_rls").forwards(apps, schema_editor)
    import_module("todos.migrations.0008_anhaenge_rls").forwards(apps, schema_editor)
    import_module("todos.migrations.0010_serien_rls").forwards(apps, schema_editor)
    for table in ("changes_changeset", "changes_changerecord"):
        schema_editor.execute(enable_rls_sql(table))
    schema_editor.execute("DROP FUNCTION IF EXISTS todos_share_target_allowed(bigint, bigint, bigint)")


class Migration(migrations.Migration):
    dependencies = [("todos", "0011_ebenen"), ("changes", "0004_anfrageschluessel_pruefsumme")]
    operations = [migrations.RunPython(forwards, backwards)]
