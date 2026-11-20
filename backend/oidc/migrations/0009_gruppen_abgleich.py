# Gruppen der Nextcloud laufend mit den Rollen abgleichen (nicht nur beim Anmelden)

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("oidc", "0008_kalender"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="sync_groups",
            field=models.BooleanField(
                default=False, db_default=False, verbose_name="Gruppen laufend abgleichen"
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="sync_groups_list",
            field=models.CharField(
                blank=True,
                db_default="",
                default="",
                max_length=500,
                verbose_name="Gruppen, die HUBIplan abgleicht",
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="groups_error",
            field=models.CharField(blank=True, db_default="", default="", max_length=500),
        ),
        migrations.AddField(
            model_name="client",
            name="groups_synced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
