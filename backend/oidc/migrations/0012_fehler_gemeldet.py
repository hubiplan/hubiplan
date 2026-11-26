# Nextcloud-Konten: wann ein Fehler zuletzt per Mail gemeldet wurde (#733)

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("oidc", "0011_videoraum"),
    ]

    operations = [
        migrations.AddField(
            model_name="account",
            name="error_mailed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
