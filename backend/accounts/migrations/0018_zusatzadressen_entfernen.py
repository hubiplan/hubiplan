"""Zusätzliche allauth-Adressen entfernen (Gesamtaudit 15.11., AUTH-02).

HUBIplan kennt je Konto genau eine Anmelde-E-Mail (``User.email``); eine Änderung löscht alle
allauth-Adressen (``accounts.self_service.apply_email``). Weitere Adressen konnten nur über
allauths eigene E-Mail-Verwaltung entstehen, die jetzt gesperrt ist. „Passwort vergessen“
fand Konten auch über solche Adressen. Deshalb bleiben nur Adressen, die der Anmelde-E-Mail
entsprechen. Die vorige Fassung braucht keine anderen Adressen; zurück ändert sich nichts.
"""

from django.db import migrations
from django.db.models import F
from django.db.models.functions import Lower


def zusatzadressen_entfernen(apps, schema_editor):
    EmailAddress = apps.get_model("account", "EmailAddress")
    (
        EmailAddress.objects.annotate(a=Lower("email"), b=Lower("user__email"))
        .exclude(a=F("b"))
        .delete()
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0017_darstellung_hell"),
        ("account", "0001_initial"),
    ]

    operations = [migrations.RunPython(zusatzadressen_entfernen, migrations.RunPython.noop)]
