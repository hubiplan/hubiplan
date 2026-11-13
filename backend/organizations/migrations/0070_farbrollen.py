# Farbrollen der Palette: Fließtext, Sekundärtext, Flächen, Hintergrund (Ralf 13.11.2026)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0069_kuendigung"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="palette_roles",
            field=models.JSONField(
                blank=True, db_default={}, default=dict, verbose_name="Farbrollen"
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="palette_roles_in_app",
            field=models.BooleanField(
                db_default=False, default=False, verbose_name="Farbrollen auch in HUBIplan"
            ),
        ),
    ]
