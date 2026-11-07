import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("finance", "0024_gobd_datenbank")]
    operations = [
        migrations.AddField(
            model_name="booking",
            name="split_of",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="split_parts",
                to="finance.booking",
                verbose_name="Teil der Buchung",
            ),
        ),
    ]
