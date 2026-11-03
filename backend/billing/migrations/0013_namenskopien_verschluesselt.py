import core.encfields
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('billing', '0012_mahnung_archiv')]
    operations = [
        migrations.AlterField(model_name='invoice', name='recipient_name', field=core.encfields.EncryptedCharField("Empfänger", max_length=200, strict=True)),
        migrations.AlterField(model_name='invoiceline', name='text', field=core.encfields.EncryptedCharField("Text", max_length=200, strict=True)),
        migrations.AlterField(model_name='invoiceline', name='detail', field=core.encfields.EncryptedCharField("Zusatz", max_length=200, blank=True, strict=True)),
        migrations.RunSQL(
            migrations.RunSQL.noop,
            reverse_sql="""
                DO $$ BEGIN
                    IF EXISTS (SELECT 1 FROM billing_invoice WHERE "recipient_name" LIKE 'enc1:%' OR char_length("recipient_name") > 200) OR
                    EXISTS (SELECT 1 FROM billing_invoiceline WHERE "text" LIKE 'enc1:%' OR char_length("text") > 200) OR
                    EXISTS (SELECT 1 FROM billing_invoiceline WHERE "detail" LIKE 'enc1:%' OR char_length("detail") > 200) THEN
                        RAISE EXCEPTION 'Vor der Rückmigration nur die neuen Namenskopien entschlüsseln und Längen prüfen.';
                    END IF;
                END $$;
            """,
        ),
    ]
