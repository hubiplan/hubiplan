"""Kalender-Abo: Schlüssel nur noch als Hash (Gesamtaudit 08.11., F-04).

Bestehende Links bleiben gültig: Der Hash wird aus dem Klartext gebildet, danach wird der
Klartext gelöscht. Rückweg: Die alte Fassung findet die Abos nicht mehr; Mitglieder erstellen
ihren Link dann neu.
"""

import hashlib

from django.db import migrations, models


def forwards(apps, schema_editor):
    PersonalCalendar = apps.get_model("events", "PersonalCalendar")
    for feed in PersonalCalendar.objects.exclude(key__isnull=True).exclude(key=""):
        feed.key_hash = hashlib.sha256(feed.key.encode()).hexdigest()
        feed.key = None
        feed.save(update_fields=["key", "key_hash"])


class Migration(migrations.Migration):
    dependencies = [("events", "0009_event_source_stale")]

    operations = [
        migrations.AlterField(
            model_name="personalcalendar",
            name="key",
            field=models.CharField(blank=True, max_length=40, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="personalcalendar",
            name="key_hash",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
