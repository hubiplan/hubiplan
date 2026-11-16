from django.db import migrations, models


class Migration(migrations.Migration):
    """Neues Feld mit Datenbank-Vorgabe; ältere Fassungen schreiben es nicht (abwärtsverträglich)."""

    dependencies = [
        ("honors", "0007_namenskopien_verschluesselt"),
    ]

    operations = [
        migrations.AddField(
            model_name="reignphoto",
            name="consent_confirmed",
            field=models.BooleanField(
                db_default=False,
                default=False,
                verbose_name="Einwilligung der Abgebildeten liegt vor",
            ),
        ),
    ]
