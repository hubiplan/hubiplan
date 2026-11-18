"""Zeilenschutz für die Absender der Verteiler (Gesamtaudit 15.11., AZ-14).

Die Zwischentabelle ``circulars_mailinglist_senders`` (Verteiler ↔ Konto) hatte keinen
Zeilenschutz. Eine Zeile gilt jetzt nur, wenn ihr Verteiler zur aktiven Einheit gehört,
wie beim Verteiler selbst (core 0026: ``organization_id = app.org_id``). Die Systemverarbeitung
(Eingang, Konto- und Einheitslöschung) arbeitet unter Umgehung und sieht alles.

Nur eine Regel, keine Spalten: Der bisherige Code bleibt lauffähig. Rückweg: Regel und
Zeilenschutz entfallen.
"""

from django.db import migrations

from core.rls import ORG, disable_rls_sql, enable_policy_sql

TABLE = "circulars_mailinglist_senders"
# Nur feste Bausteine aus core.rls, keine Eingaben
OWN_LIST = (
    "EXISTS (SELECT 1 FROM circulars_mailinglist l "  # noqa: S608
    f"WHERE l.id = {TABLE}.mailinglist_id AND l.organization_id = {ORG})"
)


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(enable_policy_sql(TABLE, OWN_LIST))


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(disable_rls_sql(TABLE))


class Migration(migrations.Migration):
    dependencies = [
        ("circulars", "0016_rundschreiben_zum_termin"),
        ("core", "0026_rls_mailverteiler"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
