"""Verweis auf Geschäftspartner an Buchung, Bankzeile, Quittung und Zuwendung (P2).

Nur neue, leere Spalten (NULL); die Vorfassung liest sie nicht.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0027_geschaeftspartner"),
        ("finance", "0033_umsatzsteuer"),
    ]

    operations = [
        migrations.AddField(
            model_name="bankline",
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
        migrations.AddField(
            model_name="booking",
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
        migrations.AddField(
            model_name="cashreceipt",
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
        migrations.AddField(
            model_name="donation",
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
