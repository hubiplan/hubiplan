# Audit 02.11. BP-F03: anonymisierter Rechnungsempfänger nach Ablauf der Aufbewahrungsfrist

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0009_mandat_verschluesselt"),
    ]

    operations = [
        migrations.AlterField(
            model_name="invoice",
            name="recipient_kind",
            field=models.CharField(
                choices=[
                    ("member", "Mitglied"),
                    ("department", "Abteilung"),
                    ("club", "Verein"),
                    ("anonymized", "anonymisiert"),
                ],
                max_length=12,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="invoice",
            name="rechnung_empfaenger",
        ),
        migrations.AddConstraint(
            model_name="invoice",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("membership__isnull", False), ("recipient_kind", "member")),
                    models.Q(("department__isnull", False), ("recipient_kind", "department")),
                    models.Q(("club__isnull", False), ("recipient_kind", "club")),
                    models.Q(("membership__isnull", True), ("recipient_kind", "anonymized")),
                    _connector="OR",
                ),
                name="rechnung_empfaenger",
            ),
        ),
    ]
