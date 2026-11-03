import core.encfields
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('access', '0016_bereiche')]
    operations = [
        migrations.AlterField(model_name='roleassignment', name='name', field=core.encfields.EncryptedCharField("Name (früherer Inhaber)", max_length=200, blank=True, strict=True)),
        migrations.RunSQL(
            migrations.RunSQL.noop,
            reverse_sql="""
                DO $$ BEGIN
                    IF EXISTS (SELECT 1 FROM access_roleassignment WHERE "name" LIKE 'enc1:%' OR char_length("name") > 200) THEN
                        RAISE EXCEPTION 'Vor der Rückmigration nur die neuen Namenskopien entschlüsseln und Längen prüfen.';
                    END IF;
                END $$;
            """,
        ),
    ]
