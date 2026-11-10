"""Textseiten aus Abschnitten (Konzept webseite-baukasten G4)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("website", "0041_entwurf_gestaltung")]

    operations = [
        migrations.AddField(
            model_name="websitetext",
            name="sections",
            field=models.JSONField(blank=True, default=list, verbose_name="Abschnitte"),
        ),
        migrations.AddField(
            model_name="websitetext",
            name="published_sections",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="websiterevision",
            name="sections",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
