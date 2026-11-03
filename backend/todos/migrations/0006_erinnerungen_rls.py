from django.db import migrations

from core.rls import USER, disable_rls_sql, enable_policy_sql, enable_rls_sql


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in ("todos_todoreminderconfig", "todos_todoreminder"):
        schema_editor.execute(enable_policy_sql(table, f"user_id = {USER}"))
    schema_editor.execute(enable_rls_sql("todos_todocleanupsetting"))


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        for table in ("todos_todoreminderconfig", "todos_todoreminder", "todos_todocleanupsetting"):
            schema_editor.execute(disable_rls_sql(table))


class Migration(migrations.Migration):
    dependencies = [("todos", "0005_erinnerungen")]
    operations = [migrations.RunPython(forwards, backwards)]
