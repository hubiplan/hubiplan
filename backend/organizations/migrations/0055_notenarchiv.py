"""Modul „Notenarchiv“ (Modulverzeichnis, M2c).

Nichts verschwindet: Wo Musik an ist, wird das Notenarchiv eingeschaltet (Musik setzt es
jetzt voraus). Rollen mit Musikrechten bekommen die gleichen Rechte am Notenarchiv.
Rückweg: Modul und die neuen Rechte werden wieder entfernt.
"""

from django.db import migrations

# Bearbeiten zieht Lesen mit (gespeicherte Form der Rechte)
CODES = {
    "music.edit": ("scores.edit", "scores.view"),
    "music.view": ("scores.view",),
}
NEW = {"scores.edit", "scores.view"}


def _bypass(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def forward(apps, schema_editor):
    _bypass(schema_editor)
    Organization = apps.get_model("organizations", "Organization")
    Role = apps.get_model("access", "Role")
    for org in Organization.objects.filter(type__in=("federation", "club")):
        modules = set(org.enabled_modules or [])
        if "music" in modules and "scores" not in modules:
            org.enabled_modules = sorted(modules | {"scores"})
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
        if "scores" in (org.enabled_modules or []):
            org.enabled_modules = [m for m in org.enabled_modules if m != "scores"]
            org.save(update_fields=["enabled_modules"])
    for role in Role._base_manager.iterator():
        perms = [p for p in role.permissions or [] if p not in NEW]
        if perms != list(role.permissions or []):
            Role._base_manager.filter(pk=role.pk).update(permissions=perms)


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0054_steuern_zuwendungen"),
        ("access", "0017_namenskopien_verschluesselt"),
    ]

    operations = [migrations.RunPython(forward, backward)]
