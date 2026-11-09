"""Ausgeblendete Schnellaktionen der Startseite am Konto (S-04). Leer erlaubt: Die vorige
Fassung schreibt weiter Konten, ohne das Feld zu kennen (docs/releases.md)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0013_darstellung"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="home_actions_hidden",
            field=models.JSONField(
                blank=True, null=True, verbose_name="ausgeblendete Schnellaktionen"
            ),
        ),
    ]
