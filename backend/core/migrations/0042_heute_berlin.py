"""Datumsfunktionen für Zeilenschutzregeln in der Zeitzone der Anwendung.

``CURRENT_DATE`` folgt der Zeitzone der DB-Sitzung; Django setzt sie bei USE_TZ auf UTC. Die
Anwendung rechnet mit ``timezone.localdate()`` (Europe/Berlin). Zwischen Mitternacht und 1 Uhr
(Sommerzeit 2 Uhr) sah die Datenbank deshalb noch den Vortag: Eine heute beginnende Rolle galt
dort noch nicht, eine gestern beendete noch. ``hubiplan_heute()`` liefert das Datum so, wie die
Anwendung es sieht; die Regeln stellen todos 0018 und finance 0038 darauf um.
"""

from django.conf import settings
from django.db import migrations

from core.rls import heute_funktionen_sql


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(heute_funktionen_sql(settings.TIME_ZONE))


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "DROP FUNCTION IF EXISTS public.hubiplan_heute(); "
        "DROP FUNCTION IF EXISTS public.hubiplan_datum(timestamptz);"
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0041_rls_termine_nach_oben_spalten")]
    operations = [migrations.RunPython(forwards, backwards)]
