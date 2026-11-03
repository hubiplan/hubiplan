from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0009_hilfe")]
    operations = [
        migrations.AddField(
            model_name="user", name="auth_version",
            field=models.PositiveBigIntegerField(default=0, db_default=0, editable=False),
        ),
    ]
