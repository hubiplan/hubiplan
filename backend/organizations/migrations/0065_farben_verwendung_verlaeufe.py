# Verwendung je Farbe und benannte Verläufe (Farbblatt, Ralf 10.11.2026)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0064_logo_dunkel"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="primary_color_use",
            field=models.CharField(
                blank=True, db_default="", max_length=60, verbose_name="Verwendung der Hauptfarbe"
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="accent_color_use",
            field=models.CharField(
                blank=True, db_default="", max_length=60, verbose_name="Verwendung der Zweitfarbe"
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="gradients",
            field=models.JSONField(
                blank=True, db_default=[], default=list, verbose_name="Verläufe"
            ),
        ),
    ]
