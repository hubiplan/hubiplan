from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0038_einwilligung_mitgliederliste"),
    ]

    operations = [
        migrations.AddField(
            model_name="website",
            name="menu_links",
            field=models.JSONField(blank=True, default=dict, verbose_name="Links im Menü"),
        ),
        migrations.AddField(
            model_name="website",
            name="menu_button",
            field=models.CharField(
                blank=True, max_length=40, verbose_name="Menüpunkt als Knopf"
            ),
        ),
    ]
