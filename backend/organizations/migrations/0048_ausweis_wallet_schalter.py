from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("organizations", "0047_schiessinfrastruktur")]
    operations = [
        migrations.AddField(
            model_name="organization",
            name="card_wallet_enabled",
            # db_default: Ältere Fassungen (Rückweg) legen Einheiten ohne die Spalte an
            field=models.BooleanField(
                "Mitgliedsausweis in Apple und Google Wallet anbieten",
                default=True,
                db_default=True,
                help_text="Nur wirksam, wenn der Betreiber Wallet eingerichtet hat.",
            ),
        ),
    ]
