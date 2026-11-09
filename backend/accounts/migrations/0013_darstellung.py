"""Darstellung der Web-App am Konto (X-02). Mit Vorgabe in der Datenbank: Die vorige
Fassung schreibt weiter Konten, ohne das Feld zu kennen (docs/releases.md)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0012_unterschrift_rls"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="color_scheme",
            field=models.CharField(
                choices=[("auto", "Wie Gerät"), ("light", "Hell"), ("dark", "Dunkel")],
                db_default="auto",
                default="auto",
                max_length=5,
                verbose_name="Darstellung",
            ),
        ),
    ]
