from django.db import migrations, models


class Migration(migrations.Migration):
    """Prüfwert der App am Verbindungscode (Gesamtaudit 15.11., APP-01); leer für ältere Codes,
    mit Datenbank-Vorgabe, damit die vorige Fassung weiter Codes anlegen kann."""

    dependencies = [
        ("devices", "0006_push_apns"),
    ]

    operations = [
        migrations.AddField(
            model_name="pairingcode",
            name="challenge",
            field=models.CharField(blank=True, db_default="", default="", max_length=43),
        ),
    ]
