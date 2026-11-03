import core.encfields
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("members", "0023_personen_suchmarken")]
    operations = [
        migrations.RemoveIndex(model_name="person", name="members_per_scope_i_25b465_idx"),
        migrations.AlterModelOptions(
            name="person",
            options={"ordering": ["pk"], "verbose_name": "Person", "verbose_name_plural": "Personen"},
        ),
        migrations.AlterField(
            model_name="person", name="last_name",
            field=core.encfields.EncryptedCharField("Name", max_length=100, strict=True),
        ),
        migrations.AlterField(
            model_name="person", name="first_name",
            field=core.encfields.EncryptedCharField("Vorname", max_length=100, strict=True),
        ),
        # Rückwärts vor text -> varchar(100): Chiffrat darf niemals gekürzt werden.
        migrations.RunSQL(
            migrations.RunSQL.noop,
            reverse_sql="""
                DO $$ BEGIN
                    IF EXISTS (
                        SELECT 1 FROM members_person
                        WHERE last_name LIKE 'enc1:%' OR first_name LIKE 'enc1:%'
                    ) THEN
                        RAISE EXCEPTION 'Vor der Rückmigration nur die Personennamen entschlüsseln.';
                    END IF;
                END $$;
            """,
        ),
    ]
