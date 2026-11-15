from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0049_designpaket_einheit"),
    ]

    operations = [
        migrations.AddField(
            model_name="websiteimage",
            name="credit",
            field=models.CharField(blank=True, max_length=200, verbose_name="Urheber/in"),
        ),
    ]
