from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("competitions", "0017_namenskopien_verschluesselt")]

    operations = [
        migrations.AlterField(
            model_name="competition",
            name="website_depth",
            field=models.CharField(
                choices=[
                    ("einheiten", "nur Wertung der Untereinheiten und Mannschaften"),
                    ("top3", "Preisplätze mit Namen"),
                    ("alle", "ganze Rangliste"),
                ],
                default="top3",
                max_length=10,
                verbose_name="Umfang auf der Webseite",
            ),
        ),
    ]
