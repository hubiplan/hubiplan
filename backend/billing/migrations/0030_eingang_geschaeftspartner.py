import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0029_partner_vertraege_dokumente"),
    ]

    operations = [
        migrations.AddField(
            model_name="incominginvoice",
            name="partner",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="billing.businesspartner",
                verbose_name="Geschäftspartner",
            ),
        ),
    ]
