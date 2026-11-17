"""Termine nach oben: Spalten in der Regel für events_event eindeutig benennen.

Gesamtaudit 15.11., AZ-04. Die Regel aus 0020/0022 prüfte die Weitergabe nach oben mit
``EXISTS (SELECT 1 FROM organizations_organization o WHERE o.id = organization_id ...)``.
Seit organizations 0014 hat ``organizations_organization`` selbst eine Spalte
``organization_id`` (Datenbereich einer Untereinheit). PostgreSQL bindet den unbenannten
Namen an die innerste Tabelle, also an ``o``. Die Bedingung lautete damit
``o.id = o.organization_id`` und traf für Vereine nie zu: Der Vorstand eines Dachverbands
sah die nach oben freigegebenen Termine seiner Vereine nicht. ``share_up`` war ebenfalls
unbenannt und griff nur deshalb auf ``events_event``, weil die Einheit keine solche Spalte hat.

Die Regel nennt jetzt beide Spalten mit ``events_event.``; sonst bleibt sie wie in 0022.
Nur die Regel ändert sich, keine Spalte: Ältere Fassungen laufen unverändert weiter, der
Rückweg stellt den Text aus 0022 wieder her.
"""

from django.db import migrations

from core.rls import ORG, SCOPE, enable_policy_sql

OWN = f"organization_id = {ORG}"
FEDERATION_SHARED = f"(organization_id = {SCOPE} AND visibility <> 'board')"
CHILD_SHARED_UP = (
    "(visibility <> 'board' AND department_id IS NULL AND EXISTS ("
    "SELECT 1 FROM organizations_organization o WHERE o.id = events_event.organization_id "
    f"AND o.parent_id = {ORG} AND COALESCE(events_event.share_up, o.events_share_up)))"
)
# Stand 0022 (fehlerhaft, nur für den Rückweg)
CHILD_SHARED_UP_0022 = (
    "(visibility <> 'board' AND department_id IS NULL AND EXISTS ("
    "SELECT 1 FROM organizations_organization o WHERE o.id = organization_id "
    f"AND o.parent_id = {ORG} AND COALESCE(share_up, o.events_share_up)))"
)
REMOTE = (
    "EXISTS (SELECT 1 FROM peering_coupling c WHERE c.remote_unit_id = organization_id "
    f"AND c.local_unit_id = {ORG} AND c.direction = 'parent' AND c.state = 'active')"
)
REMOTE_SHARED = f"(visibility <> 'board' AND {REMOTE})"

POLICIES = {
    "events_event": (f"{OWN} OR {FEDERATION_SHARED} OR {CHILD_SHARED_UP} OR {REMOTE_SHARED}", OWN),
}
OLD = {
    "events_event": (
        f"{OWN} OR {FEDERATION_SHARED} OR {CHILD_SHARED_UP_0022} OR {REMOTE_SHARED}",
        OWN,
    ),
}


def apply(policies):
    def run(apps, schema_editor):
        if schema_editor.connection.vendor == "postgresql":
            for table, (using, check) in policies.items():
                schema_editor.execute(enable_policy_sql(table, using, check))

    return run


class Migration(migrations.Migration):
    """Nur die Regel ändert sich, keine Spalte (abwärtsverträglich)."""

    dependencies = [
        ("core", "0040_joblauf"),
        ("events", "0015_db_default_rueckweg"),
        ("organizations", "0014_einheiten"),
        ("peering", "0001_initial"),
    ]

    operations = [migrations.RunPython(apply(POLICIES), apply(OLD))]
