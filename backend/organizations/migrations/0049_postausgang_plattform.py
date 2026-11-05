from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("organizations", "0048_ausweis_wallet_schalter")]
    operations = [
        migrations.AddField(
            model_name="organization",
            name="outbox_platform_content",
            # db_default: Ältere Fassungen (Rückweg) legen Einheiten ohne die Spalte an
            field=models.BooleanField(
                "Plattform-Betreuung darf Inhalte im Postausgang sehen",
                default=False,
                db_default=False,
                help_text="Text und Anhänge der Mails dieser Einheit, etwa zur Fehlersuche.",
            ),
        ),
    ]
