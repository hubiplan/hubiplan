from django.db import migrations, models


class Migration(migrations.Migration):
    """Webseite #75: Menüpunkte nur im Fuß oder im Hauptmenü und im Fuß. Neues Feld mit
    Vorgabe ``{}`` (alles wie bisher im Hauptmenü); ältere Stände lesen es nicht."""

    dependencies = [
        ("website", "0047_kopfbild_schmal"),
    ]

    operations = [
        migrations.AddField(
            model_name="website",
            name="menu_places",
            field=models.JSONField(blank=True, default=dict, verbose_name="Platz der Menüpunkte"),
        ),
    ]
