from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0070_farbrollen"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="units_in_menu",
            field=models.BooleanField(
                db_default=True, default=True, verbose_name="Menüpunkt für Untereinheiten zeigen"
            ),
        ),
    ]
