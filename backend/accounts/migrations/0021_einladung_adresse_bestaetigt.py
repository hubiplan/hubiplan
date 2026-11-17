"""Unbestätigte allauth-Adressen angemeldeter Konten bestätigen (#599).

Bisher legte schon das Erzeugen eines Einladungs- oder Passwortlinks eine unbestätigte
Adresszeile an. allauth verweigert dann die Zwei-Faktor-Einrichtung, obwohl HUBIplan keine
Bestätigungsmail verschickt. Konten, die sich schon angemeldet haben, kamen über einen Link
an die Anmelde-E-Mail oder wurden mit ihr von Verwaltenden angelegt; ihre Adresszeile zur
Anmelde-E-Mail gilt als bestätigt. Konten, die die Einladung noch nicht genutzt haben,
bestätigen beim Festlegen des Passworts. Die vorige Fassung liest das Feld nur; zurück
ändert sich nichts.
"""

from django.db import migrations
from django.db.models import F
from django.db.models.functions import Lower


def adressen_bestaetigen(apps, schema_editor):
    EmailAddress = apps.get_model("account", "EmailAddress")
    (
        EmailAddress.objects.filter(verified=False, user__last_login__isnull=False)
        .annotate(a=Lower("email"), b=Lower("user__email"))
        .filter(a=F("b"))
        .update(verified=True)
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0020_db_default_rueckweg"),
        ("account", "0001_initial"),
    ]

    operations = [migrations.RunPython(adressen_bestaetigen, migrations.RunPython.noop)]
