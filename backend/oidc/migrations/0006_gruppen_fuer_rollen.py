from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("oidc", "0005_konten_deaktivieren")]

    operations = [
        migrations.AddField(
            model_name="client",
            name="role_groups",
            field=models.JSONField(blank=True, default=dict, verbose_name="Gruppen für Rollen"),
        ),
    ]
