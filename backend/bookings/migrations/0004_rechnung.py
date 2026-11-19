import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Rechnung über die Miete einer Buchung (nullbar, abwärtsverträglich)."""

    dependencies = [
        ("bookings", "0003_mitglied"),
        ("billing", "0038_anmeldungen"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="invoice",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="billing.invoice",
            ),
        ),
    ]
