from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("events", "0006_fremde_kalender")]
    operations = [
        migrations.AddField(
            model_name="externalcalendar",
            name="last_successful_sync_at",
            field=models.DateTimeField(blank=True, null=True),
        )
    ]
