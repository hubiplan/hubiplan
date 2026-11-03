import core.encfields
from django.db import migrations

DROP_TRIGGER = "DROP TRIGGER members_person_marks_invalidate ON members_person;"
CREATE_TRIGGER = """
CREATE TRIGGER members_person_marks_invalidate
BEFORE UPDATE OF scope_id, last_name, first_name, birth_date, birth_year_only
ON members_person FOR EACH ROW EXECUTE FUNCTION members_person_marks_invalidate();
"""


class Migration(migrations.Migration):
    dependencies = [("members", "0023_personen_suchmarken")]
    operations = [
        # PostgreSQL sperrt den Typwechsel bei spaltengebundenen Triggern. Alle
        # Schritte laufen atomar; außerhalb der Migration bleibt der Schutz aktiv.
        migrations.RunSQL(DROP_TRIGGER, reverse_sql=CREATE_TRIGGER),
        migrations.RemoveIndex(model_name="person", name="members_per_scope_i_25b465_idx"),
        migrations.AlterModelOptions(
            name="person",
            options={
                "ordering": ["pk"],
                "verbose_name": "Person",
                "verbose_name_plural": "Personen",
            },
        ),
        migrations.AlterField(
            model_name="person",
            name="last_name",
            field=core.encfields.EncryptedCharField("Name", max_length=100, strict=True),
        ),
        migrations.AlterField(
            model_name="person",
            name="first_name",
            field=core.encfields.EncryptedCharField("Vorname", max_length=100, strict=True),
        ),
        migrations.RunSQL(CREATE_TRIGGER, reverse_sql=DROP_TRIGGER),
        # Rückwärts vor text -> varchar(100): Chiffrat darf niemals gekürzt werden.
        migrations.RunSQL(
            migrations.RunSQL.noop,
            reverse_sql="""
                DO $$ BEGIN
                    IF EXISTS (
                        SELECT 1 FROM members_person
                        WHERE last_name LIKE 'enc1:%' OR first_name LIKE 'enc1:%'
                            OR char_length(last_name) > 100 OR char_length(first_name) > 100
                    ) THEN
                        RAISE EXCEPTION 'Vor der Rückmigration nur die Personennamen entschlüsseln und Längen prüfen.';
                    END IF;
                END $$;
            """,
        ),
    ]
