from django.db import migrations

from core.rls import ORG, USER, disable_rls_sql, enable_policy_sql


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        rule = f"(created_by_id = {USER} OR owner_id = {USER}) AND (organization_id = {ORG} OR {ORG} IS NULL)"
        schema_editor.execute(enable_policy_sql("todos_todo", rule))
    Role = apps.get_model("access", "Role")
    for role in Role._base_manager.all():
        permissions = role.permissions or []
        if permissions and not any(p.startswith("todos.") for p in permissions):
            level = "edit" if role.is_board or set(permissions) & {"roles.edit", "roles.manage"} else "view"
            role.permissions = [*permissions, f"todos.{level}"]
            role.save(update_fields=["permissions"])


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(disable_rls_sql("todos_todo"))
    Role = apps.get_model("access", "Role")
    for role in Role._base_manager.all():
        role.permissions = [p for p in role.permissions or [] if not p.startswith("todos.")]
        role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("todos", "0001_initial"), ("access", "0017_namenskopien_verschluesselt")]
    operations = [migrations.RunPython(forwards, backwards)]
