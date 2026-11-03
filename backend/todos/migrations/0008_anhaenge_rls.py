from django.db import migrations

from core.rls import USER, disable_rls_sql, enable_policy_sql


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    # Die übergeordnete Aufgabe unterliegt bereits ihrer eigenen RLS-Regel.
    parent = "EXISTS (SELECT 1 FROM todos_todo t WHERE t.id = todo_id AND t.organization_id = todos_todoattachment.organization_id)"
    from importlib import import_module

    grant = import_module("todos.migrations.0004_freigaben_rls").grant(True)
    edit = f"EXISTS (SELECT 1 FROM todos_todo WHERE id = todo_id AND (owner_id = {USER} OR (shared AND {grant})))"
    schema_editor.execute(enable_policy_sql("todos_todoattachment", parent, f"{parent} AND {edit}"))


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(disable_rls_sql("todos_todoattachment"))


class Migration(migrations.Migration):
    dependencies = [("todos", "0007_anhaenge")]
    operations = [migrations.RunPython(forwards, backwards)]
