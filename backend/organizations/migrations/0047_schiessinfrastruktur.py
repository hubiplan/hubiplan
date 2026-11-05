from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("organizations", "0046_loeschfrist_schonfrist")]
    operations = [
        migrations.AddField(
            model_name="organization",
            name="shooting_facilities",
            field=models.JSONField(
                "verfügbare Schießinfrastruktur", default=None, null=True, blank=True
            ),
        ),
    ]
