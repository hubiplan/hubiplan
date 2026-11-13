from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0046_ki_bilder_beitraege"),
    ]

    operations = [
        migrations.AddField(
            model_name="websiteimage",
            name="header_narrow",
            field=models.BooleanField(
                default=False, verbose_name="Kopfbild für schmale Bildschirme"
            ),
        ),
    ]
