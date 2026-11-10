"""Eingehende E-Rechnungen im Hintergrund prüfen (Gesamtaudit 10.11., S05).

Rückweg: Die Spalte hat einen Standardwert in der Datenbank; die Vorfassung legt Eingänge
ohne sie an und liest sie nicht. Wartende Eingänge („pending“) prüft die Vorfassung nicht
mehr; dort hilft „Erneut prüfen“.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("billing", "0024_rechnung_gobd")]
    operations = [
        migrations.AddField(
            model_name="incominginvoice",
            name="validation",
            field=models.CharField(
                choices=[("pending", "Wird geprüft"), ("done", "Geprüft")],
                db_default="done",
                default="done",
                max_length=8,
            ),
        ),
    ]
