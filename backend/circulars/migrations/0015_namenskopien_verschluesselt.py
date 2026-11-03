import core.encfields
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('circulars', '0014_empfaengerkontakt_verschluesselt')]
    operations = [
        migrations.AlterModelOptions(name='circularrecipient', options={'ordering': ['pk'], 'verbose_name': 'Empfänger eines Rundschreibens', 'verbose_name_plural': 'Empfänger von Rundschreiben'}),
        migrations.AlterField(model_name='circularrecipient', name='first_name', field=core.encfields.EncryptedCharField("Vorname", max_length=100, blank=True, strict=True)),
        migrations.AlterField(model_name='circularrecipient', name='last_name', field=core.encfields.EncryptedCharField("Name", max_length=100, blank=True, strict=True)),
        migrations.RunSQL(
            migrations.RunSQL.noop,
            reverse_sql="""
                DO $$ BEGIN
                    IF EXISTS (SELECT 1 FROM circulars_circularrecipient WHERE "first_name" LIKE 'enc1:%' OR char_length("first_name") > 100) OR
                    EXISTS (SELECT 1 FROM circulars_circularrecipient WHERE "last_name" LIKE 'enc1:%' OR char_length("last_name") > 100) THEN
                        RAISE EXCEPTION 'Vor der Rückmigration nur die neuen Namenskopien entschlüsseln und Längen prüfen.';
                    END IF;
                END $$;
            """,
        ),
    ]
