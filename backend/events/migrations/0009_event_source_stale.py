from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("events", "0008_endzeit_ausblenden")]
    operations = [
        migrations.AddField(
            model_name="event",
            name="source_stale",
            field=models.BooleanField(
                db_default=False,
                default=False,
                editable=False,
                verbose_name="Quelle veraltet (ausgeblendet)",
            ),
        )
    ]
