from django.db import migrations, models


class Migration(migrations.Migration):
    """Schalter „Titel vor dem Namen nennen“ (Standard aus). Abwärtsverträglich:
    neue Spalte mit Standardwert in der Datenbank."""

    dependencies = [
        ("website", "0044_hinweisleiste"),
    ]

    operations = [
        migrations.AddField(
            model_name="website",
            name="show_titles",
            field=models.BooleanField(
                db_default=False, default=False, verbose_name="Titel vor dem Namen nennen"
            ),
        ),
    ]
