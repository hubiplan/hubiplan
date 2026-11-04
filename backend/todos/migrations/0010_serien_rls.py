from django.db import migrations

from core.rls import ORG, USER, disable_rls_sql, enable_policy_sql


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        own = f"organization_id = {ORG} AND owner_id = {USER}"
        related = "EXISTS (SELECT 1 FROM todos_todo t WHERE t.series_id = todos_todoseries.id)"
        schema_editor.execute(enable_policy_sql("todos_todoseries", f"({own}) OR {related}"))


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(disable_rls_sql("todos_todoseries"))


class Migration(migrations.Migration):
    dependencies = [("todos", "0009_serien")]
    operations = [migrations.RunPython(forwards, backwards)]
