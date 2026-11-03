from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("cards", "0002_rls_und_rechte")]
    operations = [
        migrations.AddField(
            model_name="membercard",
            name="wallet_passes",
            field=models.JSONField(blank=True, default=dict, db_default={}),
        ),
    ]
