from django.db import migrations, models


class Migration(migrations.Migration):
    """Neues Feld mit Datenbank-Vorgabe: Ältere Fassungen legen Gäste ohne das Feld an,
    die Datenbank setzt dann „nicht angegeben“ (abwärtsverträglich)."""

    dependencies = [
        ("competitions", "0019_schiessdurchgaenge"),
    ]

    operations = [
        migrations.AddField(
            model_name="starter",
            name="guest_adult",
            field=models.BooleanField(
                db_default=False, default=False, verbose_name="Gast volljährig"
            ),
        ),
    ]
