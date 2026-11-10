"""Eigene Auswahl und Reihenfolge der Schnellaktionen am Konto (S-04). Leer erlaubt: Die vorige
Fassung schreibt weiter Konten, ohne das Feld zu kennen (docs/releases.md)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0014_schnellaktionen"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="home_actions",
            field=models.JSONField(
                blank=True, null=True, verbose_name="Auswahl der Schnellaktionen"
            ),
        ),
    ]
