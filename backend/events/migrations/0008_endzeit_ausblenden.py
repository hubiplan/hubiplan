from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("events", "0007_external_last_success")]
    operations = [
        migrations.AddField(
            model_name="event",
            name="hide_end_time",
            field=models.BooleanField(
                db_default=False, default=False, verbose_name="Endzeit auf der Webseite ausblenden"
            ),
        )
    ]
