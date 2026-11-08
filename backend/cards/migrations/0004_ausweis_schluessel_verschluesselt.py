"""Ausweis-Schlüssel verschlüsselt, Suche über Hash (Gesamtaudit 08.11., F-04).

Die Spalte ``token`` wird zu ``text``; bestehende Werte bleiben lesbar, bis der Bestandslauf
``daten_verschluesseln`` sie verschlüsselt. ``token_hash`` wird hier aus dem Klartext
gebildet, bestehende Ausweise und Ausdrucke bleiben gültig. Rückweg: möglich, solange
``daten_verschluesseln`` noch nicht lief; danach Ausweise neu erzeugen.
"""

import hashlib

from django.db import migrations, models

import core.encfields
import cards.models


def forwards(apps, schema_editor):
    MemberCard = apps.get_model("cards", "MemberCard")
    for pk, token in MemberCard.objects.values_list("pk", "token"):
        if token and not token.startswith("enc1:"):
            MemberCard.objects.filter(pk=pk).update(
                token_hash=hashlib.sha256(token.encode()).hexdigest()
            )


class Migration(migrations.Migration):
    dependencies = [("cards", "0003_membercard_wallet_passes")]

    operations = [
        migrations.AddField(
            model_name="membercard",
            name="token_hash",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="membercard",
            name="token",
            field=core.encfields.EncryptedCharField(default=cards.models.new_token, max_length=64),
        ),
    ]
