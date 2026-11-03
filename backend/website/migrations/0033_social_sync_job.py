from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("website", "0032_bildunterschriften_zeigen")]
    operations = [
        migrations.AddField(
            model_name="socialfeed",
            name="sync_job_id",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="socialfeed",
            name="sync_requested_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
