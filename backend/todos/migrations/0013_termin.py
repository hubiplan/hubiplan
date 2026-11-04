import django.db.models.deletion
from django.db import migrations, models


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("""
        CREATE FUNCTION todos_event_scope() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF current_setting('app.bypass_rls', true) = 'on' OR NEW.event_id IS NULL THEN RETURN NEW; END IF;
            IF TG_OP = 'UPDATE' AND NEW.event_id IS NOT DISTINCT FROM OLD.event_id
                THEN RETURN NEW; END IF;
            IF NEW.owner_id IS DISTINCT FROM NULLIF(current_setting('app.user_id', true), '')::bigint OR NOT EXISTS (
                SELECT 1 FROM events_event e WHERE e.id = NEW.event_id
                AND e.organization_id = NEW.organization_id
                AND e.department_id IS NOT DISTINCT FROM NEW.department_id
            ) THEN RAISE EXCEPTION 'invalid task event scope'; END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER todo_event_scope BEFORE INSERT OR UPDATE ON todos_todo
            FOR EACH ROW EXECUTE FUNCTION todos_event_scope();
    """)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "DROP TRIGGER IF EXISTS todo_event_scope ON todos_todo; "
            "DROP FUNCTION IF EXISTS todos_event_scope();"
        )


class Migration(migrations.Migration):
    dependencies = [("todos", "0012_ebenen_rls"), ("events", "0001_termine")]
    operations = [
        migrations.AddField(
            model_name="todo",
            name="event",
            field=models.ForeignKey(
                to="events.event",
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
                related_name="tasks",
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
