from django.db import migrations, models


class Migration(migrations.Migration):
    """Neue Art „Glückwunsch“ (nur Auswahlliste, keine Datenänderung). Ältere Fassungen zeigen
    die Art ohne Bezeichnung. Rückweg: Migration zurücknehmen."""

    dependencies = [
        ("circulars", "0018_infoschreiben"),
    ]

    operations = [
        migrations.AlterField(
            model_name="circular",
            name="kind",
            field=models.CharField(
                choices=[
                    ("info", "Information"),
                    ("notice", "Vereinsmitteilung"),
                    ("short", "Kurzmitteilung"),
                    ("greeting", "Glückwunsch"),
                ],
                default="info",
                max_length=10,
                verbose_name="Art",
            ),
        ),
        migrations.AlterField(
            model_name="circulartemplate",
            name="kind",
            field=models.CharField(
                choices=[
                    ("info", "Information"),
                    ("notice", "Vereinsmitteilung"),
                    ("short", "Kurzmitteilung"),
                    ("greeting", "Glückwunsch"),
                ],
                default="info",
                max_length=10,
                verbose_name="Art",
            ),
        ),
    ]
