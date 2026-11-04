from django.db import migrations

from core.rls import APP_ROLE, BYPASS, ORG, USER, enable_rls_sql

PORTAL = "NULLIF(current_setting('app.todo_portal_id', true), '')::bigint"


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"""
        CREATE FUNCTION todos_portal_allowed(task_id bigint, completing boolean)
        RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
            SELECT EXISTS (
                SELECT 1 FROM public.todos_todoportalpublication p
                JOIN public.todos_todo t ON t.id = p.todo_id
                JOIN public.portal_portalaccess a ON a.id = {PORTAL}
                JOIN public.accounts_user u ON u.id = a.user_id AND u.is_active
                JOIN public.organizations_organization o ON o.id = p.organization_id
                WHERE p.todo_id = task_id AND p.active AND o.is_active
                AND o.member_portal_enabled AND a.user_id = {USER}
                AND a.organization_id = p.organization_id AND p.organization_id = {ORG}
                AND t.organization_id = p.organization_id AND t.deleted_at IS NULL
                AND NOT t.withdrawn AND NOT t.per_unit
                AND EXISTS (SELECT 1 FROM public.members_membershipperiod m
                    WHERE m.membership_id = a.membership_id AND m.entry_date <= CURRENT_DATE
                    AND (m.exit_date IS NULL OR m.exit_date >= CURRENT_DATE))
                AND (t.department_id IS NULL OR EXISTS (
                    SELECT 1 FROM public.members_departmentmembership d
                    WHERE d.membership_id = a.membership_id AND d.valid_from <= CURRENT_DATE
                    AND (d.valid_until IS NULL OR d.valid_until >= CURRENT_DATE)
                    AND d.department_id IN (WITH RECURSIVE units AS (
                        SELECT id FROM public.organizations_organization WHERE id = t.department_id
                        UNION ALL SELECT child.id FROM public.organizations_organization child
                        JOIN units parent ON child.parent_id = parent.id WHERE child.is_active
                    ) SELECT id FROM units)))
                AND ((p.mode = 'offer' AND (NOT completing OR p.claimed_by_id = a.id))
                    OR (p.mode = 'assigned' AND EXISTS (
                        SELECT 1 FROM public.todos_todoportalgrant g
                        WHERE g.publication_id = p.id AND g.access_id = a.id
                        AND (NOT completing OR g.can_complete))))
            );
        $$;
        REVOKE ALL ON FUNCTION todos_portal_allowed(bigint, boolean) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION todos_portal_allowed(bigint, boolean) TO {APP_ROLE};
    """)
    for table in ("todos_todoportalpublication", "todos_todoportalgrant"):
        # Inhaltseinsicht kommt ausschließlich über die Aufgabe. Hier nur ACL-Metadaten.
        schema_editor.execute(enable_rls_sql(table))
    schema_editor.execute(f"""
        CREATE POLICY task_portal_read ON todos_todo FOR SELECT
            USING (todos_portal_allowed(id, false));
        CREATE POLICY task_portal_write ON todos_todo FOR UPDATE
            USING (todos_portal_allowed(id, true))
            WITH CHECK (todos_portal_allowed(id, true));
        CREATE FUNCTION todos_portal_fields() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF {BYPASS} OR {PORTAL} IS NULL THEN RETURN NEW; END IF;
            IF (to_jsonb(NEW) - ARRAY['status', 'done_at', 'done_by_id', 'version', 'updated_at'])
               IS DISTINCT FROM
               (to_jsonb(OLD) - ARRAY['status', 'done_at', 'done_by_id', 'version', 'updated_at'])
            THEN RAISE EXCEPTION 'portal may only complete task'; END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER todo_portal_fields BEFORE UPDATE ON todos_todo
            FOR EACH ROW EXECUTE FUNCTION todos_portal_fields();
    """)
    # Publikationen/Empfänger schreiben nur Eigentümer mit aktuellem Aufgabenbearbeitungsrecht.
    from importlib import import_module

    scope_access = import_module("todos.migrations.0012_ebenen_rls").scope_access(True)
    for table, owner in [
        (
            "todos_todoportalpublication",
            "EXISTS (SELECT 1 FROM todos_todo t WHERE t.id = todo_id AND t.owner_id = "
            + USER
            + ")",
        ),
        (
            "todos_todoportalgrant",
            "EXISTS (SELECT 1 FROM todos_todoportalpublication p JOIN todos_todo t ON t.id = p.todo_id WHERE p.id = publication_id AND t.owner_id = "
            + USER
            + ")",
        ),
    ]:
        schema_editor.execute(f"DROP POLICY tenant_isolation ON {table}")
        schema_editor.execute(
            f"CREATE POLICY portal_acl_read ON {table} FOR SELECT USING (organization_id = {ORG} OR {BYPASS})"
        )
        condition = f"(({scope_access}) AND {owner} AND organization_id = {ORG} AND {PORTAL} IS NULL) OR {BYPASS}"
        schema_editor.execute(
            f"CREATE POLICY portal_acl_write ON {table} FOR ALL USING ({condition}) WITH CHECK ({condition})"
        )


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("""
        DROP TRIGGER IF EXISTS todo_portal_fields ON todos_todo;
        DROP FUNCTION IF EXISTS todos_portal_fields();
        DROP POLICY IF EXISTS task_portal_read ON todos_todo;
        DROP POLICY IF EXISTS task_portal_write ON todos_todo;
        DROP FUNCTION IF EXISTS todos_portal_allowed(bigint, boolean);
    """)


class Migration(migrations.Migration):
    dependencies = [("todos", "0014_portal")]
    operations = [migrations.RunPython(forwards, backwards)]
