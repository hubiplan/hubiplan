"""Speichergrenze für Webseitenbilder je Einheit (Gesamtaudit 15.11., MCP-09).

Neue Spalte mit Datenbank-Vorgabe: Die vorige Fassung kann weiter Zeilen einfügen.
Abwärtsverträglich; Rückweg entfernt die Spalte.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0072_db_default_rueckweg"),
    ]

    operations = [
        migrations.AddField(
            model_name="platformsettings",
            name="website_image_quota_mb",
            field=models.PositiveIntegerField(
                db_default=2048,
                default=2048,
                verbose_name="Speicher für Webseitenbilder je Einheit (MB)",
            ),
        ),
    ]
