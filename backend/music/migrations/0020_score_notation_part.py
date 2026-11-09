from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("music", "0019_score_folders")]
    operations = [
        migrations.AddField(
            model_name="scoredocument",
            name="notation_part",
            field=models.CharField(blank=True, db_default="", default="", max_length=100),
        ),
    ]
