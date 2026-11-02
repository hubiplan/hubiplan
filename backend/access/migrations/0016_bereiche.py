"""Rechte als Bereiche mit drei Stufen (konzepte/berechtigungen.md, Ralf 02.11.2026).

Jede Rolle bekommt statt der früheren Einzelrechte je Bereich *lesen* (``<bereich>.view``)
oder *bearbeiten* (``<bereich>.edit``). Verlustfrei: Wo bisher jede Rolle lesen durfte
(Einstellungen, Erscheinungsbild, Termine, im Verein empfangene Rundschreiben; in
Untereinheiten Termine und Dokumente), bekommt jede Rolle mit mindestens einem Recht „lesen“.
Rollen ohne Rechte (reine Ämter) bleiben ohne Rechte.

Die Tabellen sind hier eingefroren; der Katalog in ``access/catalog.py`` darf sich ändern.
Rückweg: ``backwards`` schreibt die früheren Codes zurück (neue reine Leserechte entfallen).
"""

from django.db import migrations

ORG = {
    "members.view": ("members.view", "photos.view", "cards.view", "logins.view"),
    "members.edit": ("members.edit", "logins.edit"),
    "photos.manage": ("photos.edit",),
    "cards.manage": ("cards.edit",),
    "org.edit": ("settings.edit",),
    "audit.view": ("audit.view",),
    "roles.manage": ("roles.edit",),
    "roles.preview": ("roles.preview", "roles.view"),
    "theme.edit": ("theme.edit",),
    "export.run": ("export.lists",),
    "data.export": ("export.full",),
    "finance.view": ("finance.view",),
    "finance.edit": ("finance.edit",),
    "billing.view": ("billing.view",),
    "billing.edit": ("billing.edit",),
    "events.manage": ("events.edit",),
    "docs.view": ("docs.view",),
    "docs.manage": ("docs.edit",),
    "circulars.send": ("circulars.edit",),
    "website.content": ("webcontent.edit",),
    "website.manage": ("webcontent.edit", "website.edit"),
    "competitions.manage": ("competitions.edit", "results.edit"),
    "competitions.results": ("competitions.view", "results.edit"),
    "entries.submit": ("entries.edit",),
    "entries.manage": ("calls.edit",),
    "peering.manage": ("peering.edit",),
    "clubs.manage": ("units.edit",),
    "platform.manage": ("platform.edit",),
}
DEPT = {
    "dept.members.view": ("members.view",),
    "dept.members.edit": ("members.edit",),
    "dept.roles.manage": ("roles.edit",),
    "dept.access.manage": ("logins.edit",),
    "dept.export": ("export.lists",),
    "dept.invoices.view": ("billing.view",),
    "dept.cards.manage": ("cards.edit",),
    "dept.events.manage": ("events.edit",),
    "dept.docs.manage": ("docs.edit",),
    "dept.circulars.send": ("circulars.edit",),
    "dept.entries.submit": ("entries.edit",),
}
EXTRAS = {"export.lists": "members", "export.full": "settings", "roles.preview": "roles"}

# Bisher sah jede Rolle diese Bereiche in der Oberfläche, je Einheitenart. (Die Webseite
# lasen andere Rollen nur technisch, ohne Menüpunkt; sie bekommen dort nichts dazu.)
BASE_READ = {
    "platform": ("settings.view", "theme.view"),
    "federation": ("settings.view", "theme.view", "events.view"),
    "club": ("settings.view", "theme.view", "events.view", "circulars.view"),
}
DEPT_BASE_READ = ("events.view", "docs.view")


def new_codes(perms, *, dept: bool, org_type: str) -> list[str]:
    table = DEPT if dept else ORG
    result: set[str] = set()
    for code in perms or []:
        if isinstance(code, str):
            result.update(table.get(code, (code,)))
    if not dept and org_type != "club":
        # Zugänge der Mitglieder gibt es nur im Verein (Mitgliederbereich)
        result -= {"logins.view", "logins.edit"}
    if result:
        result.update(DEPT_BASE_READ if dept else BASE_READ.get(org_type, ()))
    for code in list(result):
        area, _, level = code.rpartition(".")
        if level == "edit":
            result.add(f"{area}.view")
    for extra, area in EXTRAS.items():
        if extra in result:
            result.add(f"{area}.view")
    result.discard("platform.view")  # Plattform: nur bearbeiten
    return sorted(result)


def old_codes(perms, *, dept: bool) -> list[str]:
    table = DEPT if dept else ORG
    back: dict[str, set[str]] = {}
    special = {"competitions.results", "roles.preview", "website.manage"}
    for old, news in table.items():
        # Nur der Hauptcode führt zurück (members.view → members.view, nicht photos.view)
        if old not in special:
            back.setdefault(news[0], set()).add(old)
    if not dept:
        back["webcontent.edit"] = {"website.content"}
        back["website.edit"] = {"website.manage"}
        back["results.edit"] = {"competitions.results"}
        back["roles.preview"] = {"roles.preview"}
    result: set[str] = set()
    for code in perms or []:
        result.update(back.get(code, ()))
    return sorted(result)


def _bypass(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def forwards(apps, schema_editor):
    _bypass(schema_editor)
    Role = apps.get_model("access", "Role")
    for role in Role._base_manager.select_related("organization").iterator():
        dept = role.department_id is not None
        perms = new_codes(role.permissions, dept=dept, org_type=role.organization.type)
        if perms != list(role.permissions or []):
            Role._base_manager.filter(pk=role.pk).update(permissions=perms)


def backwards(apps, schema_editor):
    _bypass(schema_editor)
    Role = apps.get_model("access", "Role")
    for role in Role._base_manager.iterator():
        perms = old_codes(role.permissions, dept=role.department_id is not None)
        Role._base_manager.filter(pk=role.pk).update(permissions=perms)


class Migration(migrations.Migration):
    dependencies = [
        ("access", "0015_name_oeffentlich"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
