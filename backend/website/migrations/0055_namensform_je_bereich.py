# Issue #709: Namensform je Bereich und neue Namensform „V. Nachname“

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0054_veranstaltungsseite"),
    ]

    operations = [
        migrations.AddField(
            model_name="website",
            name="name_formats",
            field=models.JSONField(
                blank=True, db_default={}, default=dict, verbose_name="Namensform je Bereich"
            ),
        ),
        migrations.AlterField(
            model_name="website",
            name="name_format",
            field=models.CharField(
                choices=[
                    ("full", "Vorname Name"),
                    ("short", "V. Nachname"),
                    ("initial", "Vorname N."),
                ],
                default="full",
                max_length=10,
                verbose_name="Namensform",
            ),
        ),
    ]
