from django.db import migrations, models


class Migration(migrations.Migration):
    """Schalter je Gerät für Hinweise der Verwaltung; mit Datenbank-Vorgabe, damit die vorige
    Fassung weiter Geräte anlegen kann."""

    dependencies = [
        ("devices", "0007_kopplung_pruefwert"),
    ]

    operations = [
        migrations.AddField(
            model_name="device",
            name="admin_push",
            field=models.BooleanField(db_default=True, default=True),
        ),
    ]
