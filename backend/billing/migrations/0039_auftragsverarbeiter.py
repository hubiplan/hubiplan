"""Geschäftspartner-Vereinbarung der Art „Auftragsverarbeitungsvertrag“.

Nur die Auswahl wächst; Rückweg ohne Datenänderung (vorhandene „dpa“-Werte bleiben stehen).
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0038_anmeldungen"),
    ]

    operations = [
        migrations.AlterField(
            model_name="partneragreement",
            name="kind",
            field=models.CharField(
                choices=[
                    ("sponsoring", "Sponsoring"),
                    ("framework", "Rahmenvereinbarung"),
                    ("contract", "Vertrag"),
                    ("dpa", "Auftragsverarbeitungsvertrag"),
                    ("other", "Sonstige Vereinbarung"),
                ],
                default="sponsoring",
                max_length=12,
            ),
        ),
    ]
