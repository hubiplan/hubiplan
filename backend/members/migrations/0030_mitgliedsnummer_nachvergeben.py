"""Bestehende Mitglieder ohne Mitgliedsnummer bekommen eine (Nachvergabe).

Abwärtsverträglich: nur Daten, keine Spalten. Rückweg lässt die Nummern stehen.
"""

from django.db import migrations


def fill(apps, schema_editor):
    from core.tenancy import rls_bypass
    from members.services import fill_missing_club_numbers

    with rls_bypass():
        fill_missing_club_numbers(apps.get_model("members", "Membership"))


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0029_geburtsdatum_freiwillig"),
    ]

    operations = [
        migrations.RunPython(fill, migrations.RunPython.noop),
    ]
