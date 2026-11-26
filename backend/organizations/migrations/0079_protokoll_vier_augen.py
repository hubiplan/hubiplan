from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0078_koeder_ausloesungen"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="minutes_four_eyes",
            field=models.BooleanField(
                db_default=True,
                default=True,
                verbose_name="Protokolle bestätigen zwei verschiedene Personen",
            ),
        ),
    ]
