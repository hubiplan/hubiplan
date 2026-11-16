"""Optionaler Titel je Träger einer Ehrung (#518), z. B. „Ehrenhauptmann“ bei der
Ehrung „Ehrenmitglied“. Die Webseite zeigt ihn statt des Namens der Ehrung.

Abwärtsverträglich: neue Spalte mit leerer Vorgabe (auch in der Datenbank), die
Vorfassung schreibt weiter ohne sie; der Rückweg entfernt nur die Spalte.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("members", "0034_erziehungsberechtigte")]

    operations = [
        migrations.AddField(
            model_name="honorarytitleaward",
            name="display_title",
            field=models.CharField(
                blank=True, db_default="", default="", max_length=100, verbose_name="Titel"
            ),
        ),
    ]
