"""Zusätzliche Spalten bleiben mit der vorherigen Fassung beschreibbar.

Der Trigger entwertet Marken auch bei alten Writern und direkten SQL-Änderungen.
Die Anwendung füllt sie innerhalb derselben Transaktion wieder auf. Ein gestoppter
Bestandslauf verliert keine Treffer: unmarkierte Zeilen werden weiter geprüft.
"""

from django.db import migrations, models

TRIGGER = """
CREATE FUNCTION members_person_marks_invalidate() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(OLD.scope_id, OLD.last_name, OLD.first_name, OLD.birth_date, OLD.birth_year_only)
        IS DISTINCT FROM
       ROW(NEW.scope_id, NEW.last_name, NEW.first_name, NEW.birth_date, NEW.birth_year_only)
    THEN
        NEW.last_birth_mark := '';
        NEW.first_birth_mark := '';
        NEW.last_year_mark := '';
        NEW.first_year_mark := '';
        NEW.marks_version := 0;
        NEW.marks_key_id := NULL;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER members_person_marks_invalidate
BEFORE UPDATE OF scope_id, last_name, first_name, birth_date, birth_year_only
ON members_person FOR EACH ROW EXECUTE FUNCTION members_person_marks_invalidate();
"""


class Migration(migrations.Migration):
    dependencies = [("members", "0022_geburtsdatum_verschluesselt")]
    operations = [
        *[
            migrations.AddField(
                model_name="person",
                name=name,
                field=models.CharField(
                    max_length=22,
                    blank=True,
                    default="",
                    db_default="",
                    editable=False,
                ),
            )
            for name in ("last_birth_mark", "first_birth_mark", "last_year_mark", "first_year_mark")
        ],
        migrations.AddField(
            model_name="person",
            name="marks_version",
            field=models.PositiveSmallIntegerField(default=0, db_default=0, editable=False),
        ),
        migrations.AddField(
            model_name="person",
            name="marks_key_id",
            field=models.BigIntegerField(null=True, editable=False),
        ),
        *[
            migrations.AddIndex(
                model_name="person",
                index=models.Index(fields=["scope", field], name=name),
            )
            for field, name in (
                ("last_birth_mark", "person_last_birth_mark"),
                ("first_birth_mark", "person_first_birth_mark"),
                ("last_year_mark", "person_last_year_mark"),
                ("first_year_mark", "person_first_year_mark"),
            )
        ],
        migrations.RunSQL(
            TRIGGER,
            reverse_sql="""
                DROP TRIGGER members_person_marks_invalidate ON members_person;
                DROP FUNCTION members_person_marks_invalidate();
            """,
        ),
    ]
