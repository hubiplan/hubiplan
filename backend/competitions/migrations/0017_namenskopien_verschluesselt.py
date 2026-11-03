import core.encfields
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('competitions', '0016_result_ownership')]
    operations = [
        migrations.AlterModelOptions(name='starter', options={'ordering': ['pk'], 'verbose_name': 'Starter', 'verbose_name_plural': 'Starter'}),
        migrations.AlterField(model_name='starter', name='name', field=core.encfields.EncryptedCharField("Name", max_length=200, strict=True)),
        migrations.AlterField(model_name='shootoffentry', name='name', field=core.encfields.EncryptedCharField("Schütze", max_length=200, blank=True, strict=True)),
        migrations.AlterField(model_name='prize', name='winner_name', field=core.encfields.EncryptedCharField("errungen von", max_length=200, blank=True, strict=True)),
        migrations.AlterField(model_name='shot', name='name', field=core.encfields.EncryptedCharField("Schütze", max_length=200, blank=True, strict=True)),
        migrations.AlterField(model_name='awardgrant', name='name', field=core.encfields.EncryptedCharField("Name", max_length=200, strict=True)),
        migrations.RunSQL(
            migrations.RunSQL.noop,
            reverse_sql="""
                DO $$ BEGIN
                    IF EXISTS (SELECT 1 FROM competitions_starter WHERE "name" LIKE 'enc1:%' OR char_length("name") > 200) OR
                    EXISTS (SELECT 1 FROM competitions_shootoffentry WHERE "name" LIKE 'enc1:%' OR char_length("name") > 200) OR
                    EXISTS (SELECT 1 FROM competitions_prize WHERE "winner_name" LIKE 'enc1:%' OR char_length("winner_name") > 200) OR
                    EXISTS (SELECT 1 FROM competitions_shot WHERE "name" LIKE 'enc1:%' OR char_length("name") > 200) OR
                    EXISTS (SELECT 1 FROM competitions_awardgrant WHERE "name" LIKE 'enc1:%' OR char_length("name") > 200) OR
                    EXISTS (SELECT 1 FROM competitions_certificatetemplate WHERE "signers" ? 'enc1') THEN
                        RAISE EXCEPTION 'Vor der Rückmigration nur die neuen Namenskopien entschlüsseln und Längen prüfen.';
                    END IF;
                END $$;
            """,
        ),
    ]
