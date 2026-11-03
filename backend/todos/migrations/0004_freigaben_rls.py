from django.db import migrations

from core.rls import ORG, USER, disable_rls_sql, enable_policy_sql, enable_rls_sql


def grant(edit=False):
    level = "AND s.level = 'edit'" if edit else ""
    selected = "NULLIF(current_setting('app.todo_role_id', true), '')::bigint"
    preview_grant = "" if edit else f"OR s.role_id = {selected}"
    return f"""EXISTS (
        SELECT 1 FROM todos_todoshare s
        WHERE s.todo_id = todos_todo.id AND s.target_org_id = {ORG} {level}
        AND (s.user_id = {USER} {preview_grant} OR EXISTS (
            SELECT 1 FROM access_roleassignment a
            WHERE a.role_id = s.role_id AND a.valid_from <= CURRENT_DATE
            AND (a.valid_until IS NULL OR a.valid_until >= CURRENT_DATE)
            AND (a.user_id = {USER} OR EXISTS (
                SELECT 1 FROM portal_portalaccess p
                WHERE p.membership_id = a.membership_id AND p.user_id = {USER}
            ))
        ))
    )"""


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(enable_rls_sql("todos_todoshare"))
    schema_editor.execute(enable_rls_sql("todos_todonotice"))
    schema_editor.execute(enable_policy_sql("todos_todopreference", f"user_id = {USER}"))
    local = f"organization_id = {ORG}"
    own = f"(created_by_id = {USER} OR owner_id = {USER})"
    read = f"({local} AND ({own} OR (shared AND {grant()}))) OR ({ORG} IS NULL AND {own} AND NOT shared)"
    write = f"({local} AND (owner_id = {USER} OR (shared AND {grant(True)})))"
    schema_editor.execute(enable_policy_sql("todos_todo", read, write))


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in ("todos_todoshare", "todos_todopreference", "todos_todonotice"):
        schema_editor.execute(disable_rls_sql(table))
    rule = f"(created_by_id = {USER} OR owner_id = {USER}) AND (organization_id = {ORG} OR {ORG} IS NULL)"
    schema_editor.execute(enable_policy_sql("todos_todo", rule))


class Migration(migrations.Migration):
    dependencies = [("todos", "0003_freigaben")]
    operations = [migrations.RunPython(forwards, backwards)]
