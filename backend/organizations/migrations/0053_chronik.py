"""Modul „Chronik“ (Modulverzeichnis, Schritt M2b).

Nichts verschwindet: Wo die Webseite eine Chronik (Textseite „geschichte“) hat, wird das
Modul eingeschaltet; bei der Webseite einer Untereinheit beim Verein. Rollen, die Inhalte der
Webseite bearbeiten oder lesen, dürfen die Chronik ebenso pflegen oder lesen.
Rückweg: Modul und die neuen Rechte werden wieder entfernt.
"""

from django.db import migrations

# Bearbeiten zieht Lesen mit (gespeicherte Form der Rechte)
CODES = {
    "webcontent.edit": ("chronicle.edit", "chronicle.view"),
    "webcontent.view": ("chronicle.view",),
}
NEW = {"chronicle.edit", "chronicle.view"}


def _bypass(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def forward(apps, schema_editor):
    _bypass(schema_editor)
    Organization = apps.get_model("organizations", "Organization")
    WebsiteText = apps.get_model("website", "WebsiteText")
    Role = apps.get_model("access", "Role")
    owners = set()
    texts = WebsiteText.objects.filter(kind="page", slug="geschichte")
    for org_id in texts.values_list("website__organization_id", flat=True).distinct():
        org = Organization.objects.filter(pk=org_id).first()
        while org is not None and org.type == "unit":
            org = Organization.objects.filter(pk=org.organization_id).first()
        if org is not None and org.type in ("federation", "club"):
            owners.add(org.pk)
    for org in Organization.objects.filter(pk__in=owners):
        modules = set(org.enabled_modules or [])
        if "chronicle" not in modules:
            org.enabled_modules = sorted(modules | {"chronicle"})
            org.save(update_fields=["enabled_modules"])
    for role in Role._base_manager.filter(department__isnull=True).iterator():
        perms = list(role.permissions or [])
        extra = []
        for old, news in CODES.items():
            if old in perms:
                extra += [n for n in news if n not in perms and n not in extra]
        if extra:
            Role._base_manager.filter(pk=role.pk).update(permissions=perms + extra)


def backward(apps, schema_editor):
    _bypass(schema_editor)
    Organization = apps.get_model("organizations", "Organization")
    Role = apps.get_model("access", "Role")
    for org in Organization.objects.all():
        if "chronicle" in (org.enabled_modules or []):
            org.enabled_modules = [m for m in org.enabled_modules if m != "chronicle"]
            org.save(update_fields=["enabled_modules"])
    for role in Role._base_manager.iterator():
        perms = [p for p in role.permissions or [] if p not in NEW]
        if perms != list(role.permissions or []):
            Role._base_manager.filter(pk=role.pk).update(permissions=perms)


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0052_neue_module"),
        ("access", "0017_namenskopien_verschluesselt"),
        ("website", "0038_einwilligung_mitgliederliste"),
    ]

    operations = [migrations.RunPython(forward, backward)]
