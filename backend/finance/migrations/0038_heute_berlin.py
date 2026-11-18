"""GoBD-Aufbewahrung rechnet mit dem Datum der Anwendung statt mit CURRENT_DATE (UTC).

``finance_gobd_heute()`` (0032) fiel ohne Testdatum auf ``current_date`` zurück und lag damit
zwischen Mitternacht und 1 Uhr (Sommerzeit 2 Uhr) einen Tag hinter ``timezone.localdate()``.
Jetzt gilt ``hubiplan_heute()`` (core 0042); das Testdatum bleibt vorrangig.
"""

from django.db import migrations

from core.rls import heute_umstellen

FUNKTIONEN = ("finance_gobd_heute",)


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        heute_umstellen(schema_editor, r"finance\_%", FUNKTIONEN, vor=True)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        heute_umstellen(schema_editor, r"finance\_%", FUNKTIONEN, vor=False)


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0037_festschreibung_neue_buchungen"),
        ("core", "0042_heute_berlin"),
    ]
    operations = [migrations.RunPython(forwards, backwards)]
