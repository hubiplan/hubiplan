"""Voraussetzung je Dienst (Modul Qualifikationen): Hinweis bei der Einteilung.

Die Art gehört zur Organisation des Dienstes (Prüfung in der Datenbank).
Rückweg: Spalte und Prüfung entfallen, Dienste bleiben unverändert.
"""

import django.db.models.deletion
from django.db import migrations, models

GUARD = """
    CREATE FUNCTION duty_qualification_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.qualification_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM qualifications_qualificationtype
          WHERE id = NEW.qualification_id AND organization_id = NEW.organization_id
      ) THEN
        RAISE EXCEPTION 'helper scope mismatch' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END $$;
"""


def guard(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(GUARD)
    schema_editor.execute("""CREATE TRIGGER duty_qualification_guard BEFORE INSERT OR UPDATE
        ON helpers_duty FOR EACH ROW EXECUTE FUNCTION duty_qualification_guard()""")


def no_guard(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP TRIGGER IF EXISTS duty_qualification_guard ON helpers_duty")
    schema_editor.execute("DROP FUNCTION IF EXISTS duty_qualification_guard()")


class Migration(migrations.Migration):

    dependencies = [
        ("helpers", "0003_kontingente"),
        ("qualifications", "0001_qualifikationen"),
    ]

    operations = [
        migrations.AddField(
            model_name="duty",
            name="qualification",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="qualifications.qualificationtype",
                verbose_name="Voraussetzung",
            ),
        ),
        migrations.RunPython(guard, no_guard),
    ]
