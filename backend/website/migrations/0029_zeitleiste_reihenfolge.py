"""Zeitleiste der Chronik wahlweise mit den neuesten Einträgen oben (Ralf 02.11.)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("website", "0028_chronik_zeitleiste")]

    operations = [
        migrations.AddField(
            model_name="websitetext",
            name="timeline_newest_first",
            field=models.BooleanField(default=False, verbose_name="neueste Einträge oben"),
        ),
        migrations.AddField(
            model_name="websitetext",
            name="published_timeline_newest_first",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="websiterevision",
            name="timeline_newest_first",
            field=models.BooleanField(default=False),
        ),
    ]
