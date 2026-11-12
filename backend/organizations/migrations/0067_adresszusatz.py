from django.db import migrations, models

HELP = "z. B. c/o Firma oder Gebäude; steht über Straße und Hausnummer."


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0066_geschaeftspartner_im_menue"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="address_extra",
            field=models.CharField(
                blank=True,
                db_default="",
                default="",
                help_text=HELP,
                max_length=200,
                verbose_name="Adresszusatz",
            ),
        ),
        migrations.AddField(
            model_name="imprint",
            name="address_extra",
            field=models.CharField(
                blank=True,
                db_default="",
                default="",
                help_text=HELP,
                max_length=200,
                verbose_name="Adresszusatz",
            ),
        ),
    ]
