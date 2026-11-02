# Fachfrage FQ10 (Audit 02.11.): Löschsperre je Geschäftsjahr

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0020_bankzeile_iban_verschluesselt"),
    ]

    operations = [
        migrations.AddField(
            model_name="yearclosing",
            name="retention_hold",
            field=models.CharField(
                blank=True, db_default="", max_length=500, verbose_name="Löschsperre (Grund)"
            ),
        ),
        migrations.AddField(
            model_name="yearclosing",
            name="retention_hold_by_name",
            field=models.CharField(
                blank=True, db_default="", max_length=200, verbose_name="Löschsperre gesetzt von"
            ),
        ),
        migrations.AddField(
            model_name="yearclosing",
            name="retention_hold_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Löschsperre gesetzt am"),
        ),
    ]
