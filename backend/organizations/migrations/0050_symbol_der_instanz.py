from django.db import migrations, models

import organizations.models


class Migration(migrations.Migration):
    dependencies = [("organizations", "0049_postausgang_plattform")]

    operations = [
        migrations.AddField(
            model_name="platformsettings",
            name="brand_icon",
            field=models.ImageField(
                blank=True,
                upload_to=organizations.models.brand_icon_path,
                verbose_name="Symbol der Instanz",
            ),
        ),
    ]
