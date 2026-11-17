"""Partnernummer je Einheit eindeutig (Gesamtaudit 15.11., PF-25).

Vorher konnten gleichzeitige Anlagen dieselbe Nummer bekommen. Doppelte Nummern werden vor
der Eindeutigkeit aufgelöst: Der ältere Partner (kleinere ID) behält seine Nummer, jeder weitere
bekommt die nächste freie „GP-xxxx“. Jede Umnummerierung steht im Änderungsprotokoll der
Einheit (alte und neue Nummer). Belege und Dokumente, die die alte Nummer als Text tragen,
bleiben unverändert.

Rückweg: Die Eindeutigkeit fällt weg, die neuen Nummern bleiben. Die vorige Fassung läuft mit
der Eindeutigkeit weiter (sie vergibt Nummern nur ohne Sperre).
"""

from django.db import migrations, models


def renumber(apps, schema_editor):
    from billing.partners import resolve_duplicate_numbers

    resolve_duplicate_numbers()


class Migration(migrations.Migration):
    # Daten und Eindeutigkeit in getrennten Transaktionen (ALTER TABLE nach UPDATE)
    atomic = False

    dependencies = [
        ("billing", "0036_anteil_waehlbar"),
        ("audit", "0008_versiegelt_unveraenderbar"),
    ]

    operations = [
        migrations.RunPython(renumber, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="businesspartner",
            constraint=models.UniqueConstraint(
                condition=models.Q(("number", ""), _negated=True),
                fields=("organization", "number"),
                name="partner_nummer_eindeutig",
            ),
        ),
    ]
