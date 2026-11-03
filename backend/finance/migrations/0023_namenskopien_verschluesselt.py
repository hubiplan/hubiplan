import core.encfields
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('finance', '0022_bankstatement_retention_dates')]
    operations = [
        migrations.AlterField(model_name='booking', name='text', field=core.encfields.EncryptedCharField("Buchungstext", max_length=200, strict=True)),
        migrations.AlterField(model_name='booking', name='counterparty', field=core.encfields.EncryptedCharField("Empfänger/Zahler", max_length=200, blank=True, strict=True)),
        migrations.AlterField(model_name='yearclosing', name='purged_by_name', field=core.encfields.EncryptedCharField("bereinigt von", max_length=200, blank=True, db_default="", strict=True)),
        migrations.AlterField(model_name='yearclosing', name='retention_hold_by_name', field=core.encfields.EncryptedCharField(
        "Löschsperre gesetzt von", max_length=200, blank=True, db_default="", strict=True)),
        migrations.AlterField(model_name='reopenedclosing', name='closed_by_name', field=core.encfields.EncryptedCharField("abgeschlossen von", max_length=200, blank=True, strict=True)),
        migrations.AlterField(model_name='reopenedclosing', name='reopened_by_name', field=core.encfields.EncryptedCharField("aufgehoben von", max_length=200, blank=True, strict=True)),
        migrations.AlterField(model_name='cashreceipt', name='counterparty_name', field=core.encfields.EncryptedCharField("Name der Gegenseite", max_length=200, strict=True)),
        migrations.AlterField(model_name='cashreceipt', name='treasurer_name', field=core.encfields.EncryptedCharField(max_length=200, blank=True, strict=True)),
        migrations.AlterField(model_name='donationstatement', name='donor_name', field=core.encfields.EncryptedCharField("Zuwendender", max_length=200, strict=True)),
        migrations.AlterField(model_name='donationstatement', name='signer_name', field=core.encfields.EncryptedCharField("unterschrieben von", max_length=200, blank=True, strict=True)),
        migrations.AlterField(model_name='donation', name='donor_name', field=core.encfields.EncryptedCharField("Zuwendender", max_length=200, strict=True)),
        migrations.AlterField(model_name='bankline', name='name', field=core.encfields.EncryptedCharField("Gegenseite", max_length=200, blank=True, strict=True)),
        migrations.AlterField(model_name='cashcount', name='counted_by', field=core.encfields.EncryptedCharField("gezählt von", max_length=200, strict=True)),
        migrations.AlterField(model_name='cashcount', name='witness', field=core.encfields.EncryptedCharField("zweite Person", max_length=200, blank=True, strict=True)),
        migrations.AlterField(model_name='reservemovement', name='created_by_name', field=core.encfields.EncryptedCharField(max_length=200, blank=True, strict=True)),
        migrations.RunSQL(
            migrations.RunSQL.noop,
            reverse_sql="""
                DO $$ BEGIN
                    IF EXISTS (SELECT 1 FROM finance_booking WHERE "text" LIKE 'enc1:%' OR char_length("text") > 200) OR
                    EXISTS (SELECT 1 FROM finance_booking WHERE "counterparty" LIKE 'enc1:%' OR char_length("counterparty") > 200) OR
                    EXISTS (SELECT 1 FROM finance_yearclosing WHERE "purged_by_name" LIKE 'enc1:%' OR char_length("purged_by_name") > 200) OR
                    EXISTS (SELECT 1 FROM finance_yearclosing WHERE "retention_hold_by_name" LIKE 'enc1:%' OR char_length("retention_hold_by_name") > 200) OR
                    EXISTS (SELECT 1 FROM finance_reopenedclosing WHERE "closed_by_name" LIKE 'enc1:%' OR char_length("closed_by_name") > 200) OR
                    EXISTS (SELECT 1 FROM finance_reopenedclosing WHERE "reopened_by_name" LIKE 'enc1:%' OR char_length("reopened_by_name") > 200) OR
                    EXISTS (SELECT 1 FROM finance_cashreceipt WHERE "counterparty_name" LIKE 'enc1:%' OR char_length("counterparty_name") > 200) OR
                    EXISTS (SELECT 1 FROM finance_cashreceipt WHERE "treasurer_name" LIKE 'enc1:%' OR char_length("treasurer_name") > 200) OR
                    EXISTS (SELECT 1 FROM finance_donationstatement WHERE "donor_name" LIKE 'enc1:%' OR char_length("donor_name") > 200) OR
                    EXISTS (SELECT 1 FROM finance_donationstatement WHERE "items" ? 'enc1') OR
                    EXISTS (SELECT 1 FROM finance_donationstatement WHERE "signer_name" LIKE 'enc1:%' OR char_length("signer_name") > 200) OR
                    EXISTS (SELECT 1 FROM finance_donation WHERE "donor_name" LIKE 'enc1:%' OR char_length("donor_name") > 200) OR
                    EXISTS (SELECT 1 FROM finance_bankline WHERE "name" LIKE 'enc1:%' OR char_length("name") > 200) OR
                    EXISTS (SELECT 1 FROM finance_bankline WHERE "details" ? 'enc1') OR
                    EXISTS (SELECT 1 FROM finance_cashcount WHERE "counted_by" LIKE 'enc1:%' OR char_length("counted_by") > 200) OR
                    EXISTS (SELECT 1 FROM finance_cashcount WHERE "witness" LIKE 'enc1:%' OR char_length("witness") > 200) OR
                    EXISTS (SELECT 1 FROM finance_reservemovement WHERE "created_by_name" LIKE 'enc1:%' OR char_length("created_by_name") > 200) THEN
                        RAISE EXCEPTION 'Vor der Rückmigration nur die neuen Namenskopien entschlüsseln und Längen prüfen.';
                    END IF;
                END $$;
            """,
        ),
    ]
