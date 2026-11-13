"""Erziehungsberechtigte (Konzept Familien, Haushalte und Firmen, H4): Kennzeichen am
Ansprechpartner. Bisherige Ansprechpartner von Personen stammen aus dem Online-Antrag
(Minderjährige, B3) und werden erziehungsberechtigt.

Abwärtsverträglich: neue Spalte mit Vorgabe; der Rückweg entfernt nur die Spalte.
"""

from django.db import migrations, models


def mark(apps, schema_editor):
    from core.tenancy import rls_bypass

    ContactPerson = apps.get_model("members", "ContactPerson")
    with rls_bypass():
        ContactPerson.objects.exclude(membership__person__kind="organization").update(
            is_guardian=True
        )


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0033_haushalt_zahlt"),
    ]

    operations = [
        migrations.AddField(
            model_name="contactperson",
            name="is_guardian",
            field=models.BooleanField(
                db_default=False, default=False, verbose_name="erziehungsberechtigt"
            ),
        ),
        migrations.RunPython(mark, migrations.RunPython.noop),
    ]
