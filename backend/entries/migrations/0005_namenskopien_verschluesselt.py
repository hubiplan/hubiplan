import core.encfields
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('entries', '0004_wettbewerb_nur_auf_wunsch')]
    operations = [
        migrations.AlterField(model_name='entryperson', name='name', field=core.encfields.EncryptedCharField("Name", max_length=200, strict=True)),
        migrations.RunSQL(
            migrations.RunSQL.noop,
            reverse_sql="""
                DO $$ BEGIN
                    IF EXISTS (SELECT 1 FROM entries_entryperson WHERE "name" LIKE 'enc1:%' OR char_length("name") > 200) THEN
                        RAISE EXCEPTION 'Vor der Rückmigration nur die neuen Namenskopien entschlüsseln und Längen prüfen.';
                    END IF;
                END $$;
            """,
        ),
    ]
