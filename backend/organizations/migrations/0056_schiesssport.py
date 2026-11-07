"""Modul „Schießsport“ (Modulverzeichnis, M2c).

Nichts verschwindet: Wo Wettbewerbe an sind, wird Schießsport eingeschaltet (Scheiben,
Trefferbild, Fotoauswertung und Vogelschießen gehörten bisher zu Wettbewerbe).
Rückweg: Das Modul wird wieder entfernt.
"""

from django.db import migrations


def _bypass(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def forward(apps, schema_editor):
    _bypass(schema_editor)
    Organization = apps.get_model("organizations", "Organization")
    for org in Organization.objects.filter(type__in=("federation", "club")):
        modules = set(org.enabled_modules or [])
        if "competitions" in modules and "shooting" not in modules:
            org.enabled_modules = sorted(modules | {"shooting"})
            org.save(update_fields=["enabled_modules"])


def backward(apps, schema_editor):
    _bypass(schema_editor)
    Organization = apps.get_model("organizations", "Organization")
    for org in Organization.objects.all():
        if "shooting" in (org.enabled_modules or []):
            org.enabled_modules = [m for m in org.enabled_modules if m != "shooting"]
            org.save(update_fields=["enabled_modules"])


class Migration(migrations.Migration):
    dependencies = [("organizations", "0055_notenarchiv")]

    operations = [migrations.RunPython(forward, backward)]
