"""Aufgaben-Regeln vergleichen Zeiträume mit dem Datum der Anwendung statt mit CURRENT_DATE.

Rollen- (0004, 0012, 0017), Mitglieds- und Zuordnungszeiträume (0015, Mitgliederbereich)
wurden mit ``CURRENT_DATE`` geprüft, also in UTC. Zwischen Mitternacht und 1 Uhr (Sommerzeit
2 Uhr) sah eine Person mit heute beginnender Rolle geteilte Aufgaben nicht (404), eine gestern
beendete Rolle bestand die Prüfung der Datenbank dagegen noch. Jetzt gilt ``hubiplan_heute()``
(core 0042). Nur der Datumsvergleich ändert sich; der Rückweg setzt ``CURRENT_DATE`` wieder ein.
"""

from django.db import migrations

from core.rls import heute_umstellen

TABELLEN = r"todos\_%"
FUNKTIONEN = ("todos_portal_allowed",)


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        heute_umstellen(schema_editor, TABELLEN, FUNKTIONEN, vor=True)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        heute_umstellen(schema_editor, TABELLEN, FUNKTIONEN, vor=False)


class Migration(migrations.Migration):
    dependencies = [("todos", "0017_verbund_rls"), ("core", "0042_heute_berlin")]
    operations = [migrations.RunPython(forwards, backwards)]
