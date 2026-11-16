"""Anteiliger Beitrag wählbar: nicht anteilig, je angefangenem Monat, Quartal oder Halbjahr.

Der bisherige Schalter pro_rata (an = je Monat) wird übernommen und bleibt eine Fassung lang
als Spiegel erhalten. Neue Spalte mit db_default, daher abwärtsverträglich.
"""

from django.db import migrations, models


def uebernehmen(apps, schema_editor):
    BillingSettings = apps.get_model("billing", "BillingSettings")
    BillingSettings.objects.filter(pro_rata=True).update(pro_rata_step="month")


def zurueck(apps, schema_editor):
    BillingSettings = apps.get_model("billing", "BillingSettings")
    BillingSettings.objects.exclude(pro_rata_step="off").update(pro_rata=True)


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0035_db_default_rueckweg"),
    ]

    operations = [
        migrations.AddField(
            model_name="billingsettings",
            name="pro_rata_step",
            field=models.CharField(
                choices=[
                    ("off", "nicht anteilig (voller Beitrag)"),
                    ("month", "je angefangenem Monat"),
                    ("quarter", "je angefangenem Quartal"),
                    ("halfyear", "je angefangenem Halbjahr"),
                ],
                db_default="off",
                default="off",
                max_length=10,
                verbose_name="Beitrag bei Eintritt im laufenden Zeitraum",
            ),
        ),
        migrations.RunPython(uebernehmen, zurueck),
    ]
