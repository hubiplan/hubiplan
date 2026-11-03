from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("peering", "0013_sammelaustritt")]
    operations = [
        migrations.AddField(
            model_name="coupling",
            name="received_bytes",
            field=models.PositiveBigIntegerField(default=0, db_default=0),
        ),
        migrations.AddField(
            model_name="coupling",
            name="received_count",
            field=models.PositiveBigIntegerField(default=0, db_default=0),
        ),
        migrations.AddField(
            model_name="coupling",
            name="usage_initialized",
            field=models.BooleanField(default=False, db_default=False),
        ),
    ]
