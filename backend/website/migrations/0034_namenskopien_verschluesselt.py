import core.encfields
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('website', '0033_social_sync_job')]
    operations = [
        migrations.AlterField(model_name='heldmessage', name='recipient_name', field=core.encfields.EncryptedCharField("Empfänger", max_length=200, strict=True)),
        migrations.AlterField(model_name='heldmessage', name='sender_name', field=core.encfields.EncryptedCharField("Name", max_length=100, strict=True)),
        migrations.RunSQL(
            migrations.RunSQL.noop,
            reverse_sql="""
                DO $$ BEGIN
                    IF EXISTS (SELECT 1 FROM website_heldmessage WHERE "recipient_name" LIKE 'enc1:%' OR char_length("recipient_name") > 200) OR
                    EXISTS (SELECT 1 FROM website_heldmessage WHERE "sender_name" LIKE 'enc1:%' OR char_length("sender_name") > 100) THEN
                        RAISE EXCEPTION 'Vor der Rückmigration nur die neuen Namenskopien entschlüsseln und Längen prüfen.';
                    END IF;
                END $$;
            """,
        ),
    ]
