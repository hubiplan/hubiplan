from importlib import import_module

from django.db import migrations

from core.rls import APP_ROLE, BYPASS, ORG, USER, enable_rls_sql


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    rules = import_module("todos.migrations.0012_ebenen_rls")
    for table in ("todos_todoremoteshare", "todos_todoremotetask"):
        schema_editor.execute(enable_rls_sql(table))
        schema_editor.execute(f"DROP POLICY tenant_isolation ON {table}")
    owner = f"EXISTS (SELECT 1 FROM todos_todo t WHERE t.id = todo_id AND t.organization_id = {ORG} AND t.owner_id = {USER} AND NOT t.distributed) AND EXISTS (SELECT 1 FROM peering_coupling c WHERE c.id = coupling_id AND c.local_unit_id = {ORG})"
    parent = f"organization_id = {ORG} AND EXISTS (SELECT 1 FROM todos_todo t WHERE t.id = todo_id)"
    rules.policies(
        schema_editor,
        "todos_todoremoteshare",
        parent,
        f"({owner}) AND ({rules.scope_access(True)}) AND organization_id = {ORG}",
    )
    inbox = f"organization_id = {ORG} AND ((todo_id IS NULL AND {rules.DEPT} IS NULL AND ({rules.scope_access(True)})) OR EXISTS (SELECT 1 FROM todos_todo t WHERE t.id = todo_id))"
    rules.policies(schema_editor, "todos_todoremotetask", inbox, "false")
    # Nur Beziehungsdaten, kein Inhalt. SECURITY DEFINER vermeidet eine Rekursion
    # zwischen Aufgaben-ACL und empfangener Zuordnung.
    schema_editor.execute(f"""
        CREATE FUNCTION todos_remote_live(mapping_id bigint) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
            SELECT EXISTS (SELECT 1 FROM public.todos_todoremotetask m
                JOIN public.peering_coupling c ON c.id = m.coupling_id
                JOIN public.peering_peer p ON p.id = c.peer_id
                WHERE m.id = mapping_id AND m.active AND c.state = 'active'
                AND p.pending_keys = '{{}}'::jsonb
                AND c.options->'accept'->>'todos' = 'on');
        $$;
        REVOKE ALL ON FUNCTION todos_remote_live(bigint) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION todos_remote_live(bigint) TO {APP_ROLE};
        CREATE POLICY remote_live ON todos_todo AS RESTRICTIVE FOR SELECT
            USING ({BYPASS} OR remote_mode <> 'common' OR todos_remote_live(remote_origin_id));
        CREATE FUNCTION todos_remote_fields() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF {BYPASS} THEN RETURN NEW; END IF;
            IF TG_OP = 'INSERT' THEN
                IF NEW.remote_origin_id IS NOT NULL OR NEW.remote_mode <> '' THEN
                    RAISE EXCEPTION 'remote provenance requires checked system path';
                END IF;
            ELSE
                IF NEW.remote_origin_id IS DISTINCT FROM OLD.remote_origin_id
                    OR NEW.remote_mode IS DISTINCT FROM OLD.remote_mode THEN
                    RAISE EXCEPTION 'immutable remote provenance';
                END IF;
                IF OLD.remote_mode = 'common' AND (NEW.status IS DISTINCT FROM OLD.status
                    OR NEW.done_at IS DISTINCT FROM OLD.done_at OR NEW.done_by_id IS DISTINCT FROM OLD.done_by_id) THEN
                    RAISE EXCEPTION 'common status requires source acknowledgement';
                END IF;
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER todo_remote_fields BEFORE INSERT OR UPDATE ON todos_todo
            FOR EACH ROW EXECUTE FUNCTION todos_remote_fields();
    """)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("""
            DROP TRIGGER IF EXISTS todo_remote_fields ON todos_todo;
            DROP FUNCTION IF EXISTS todos_remote_fields();
            DROP POLICY IF EXISTS remote_live ON todos_todo;
            DROP FUNCTION IF EXISTS todos_remote_live(bigint);
        """)


class Migration(migrations.Migration):
    dependencies = [("todos", "0016_verbund")]
    operations = [migrations.RunPython(forwards, backwards)]
