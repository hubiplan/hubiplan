"""Zeitleiste der Chronik: kurze Einträge mit Jahr statt einer Textwand (Ralf 02.11.)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("website", "0027_bausteine_namen")]

    operations = [
        migrations.AddField(
            model_name="websitetext",
            name="timeline",
            field=models.JSONField(blank=True, default=list, verbose_name="Zeitleiste"),
        ),
        migrations.AddField(
            model_name="websitetext",
            name="published_timeline",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="websiterevision",
            name="timeline",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
