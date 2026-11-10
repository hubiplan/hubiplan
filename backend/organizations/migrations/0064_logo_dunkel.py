# Zweites Logo/Wappen für den Dunkelmodus (Ralf 10.11.2026)

from django.db import migrations, models

import organizations.models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0063_loeschung_vormerken"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="logo_dark",
            field=models.ImageField(
                blank=True,
                db_default="",
                upload_to=organizations.models.logo_dark_path,
                validators=[organizations.models.validate_logo],
                verbose_name="Logo/Wappen für den Dunkelmodus",
            ),
        ),
    ]
