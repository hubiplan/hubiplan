import core.encfields
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('honors', '0006_share_down')]
    operations = [
        migrations.AlterField(model_name='reign', name='name', field=core.encfields.EncryptedCharField("Name", max_length=200, blank=True, strict=True)),
        migrations.AlterField(model_name='companion', name='name', field=core.encfields.EncryptedCharField("Name", max_length=200, blank=True, strict=True)),
        migrations.RunSQL(
            migrations.RunSQL.noop,
            reverse_sql="""
                DO $$ BEGIN
                    IF EXISTS (SELECT 1 FROM honors_reign WHERE "name" LIKE 'enc1:%' OR char_length("name") > 200) OR
                    EXISTS (SELECT 1 FROM honors_companion WHERE "name" LIKE 'enc1:%' OR char_length("name") > 200) THEN
                        RAISE EXCEPTION 'Vor der Rückmigration nur die neuen Namenskopien entschlüsseln und Längen prüfen.';
                    END IF;
                END $$;
            """,
        ),
    ]
