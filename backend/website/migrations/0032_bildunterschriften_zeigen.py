"""Bildunterschriften unter Bild und Karussell wahlweise zeigen, Standard aus (Ralf 02.11.)."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0031_designpakete"),
    ]

    operations = [
        migrations.AddField(
            model_name="websiterevision",
            name="show_captions",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="websitetext",
            name="show_captions",
            field=models.BooleanField(default=False, verbose_name="Bildunterschriften zeigen"),
        ),
        migrations.AddField(
            model_name="websitetext",
            name="published_show_captions",
            field=models.BooleanField(default=False),
        ),
    ]
