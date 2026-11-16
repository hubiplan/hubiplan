from django.db import migrations, models


class Migration(migrations.Migration):
    """Neues Feld mit Datenbank-Vorgabe; ältere Fassungen schreiben es nicht (abwärtsverträglich)."""

    dependencies = [
        ("competitions", "0020_gast_volljaehrig"),
    ]

    operations = [
        migrations.AddField(
            model_name="prize",
            name="winner_adult",
            field=models.BooleanField(
                db_default=False, default=False, verbose_name="Gewinner volljährig"
            ),
        ),
    ]
