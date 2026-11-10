from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0039_menue_links_knopf"),
    ]

    operations = [
        migrations.AddField(
            model_name="website",
            name="style",
            field=models.JSONField(blank=True, default=dict, verbose_name="Stilregler"),
        ),
    ]
