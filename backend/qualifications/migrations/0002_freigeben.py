"""Neues Modul „Qualifikationen“ für bestehende Vereine und Dachverbände freigeben.

Freigegeben, nicht eingeschaltet: Die Einheit schaltet es unter Einstellungen › Module selbst
ein (neue Einheiten haben es von Anfang an). Leere Freigabe hieß bisher „wie eingeschaltet“;
sie wird dabei aus den eingeschalteten Modulen übernommen.
Rückweg: Das Modul verschwindet wieder aus Freigabe und Einschaltung.
"""

from django.db import migrations

MODULE = "qualifications"


def _bypass(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def forward(apps, schema_editor):
    _bypass(schema_editor)
    Organization = apps.get_model("organizations", "Organization")
    for org in Organization.objects.filter(type__in=("federation", "club")):
        enabled = set(org.enabled_modules or [])
        if "members" not in enabled:
            continue
        released = set(org.released_modules or enabled)
        if MODULE in released:
            continue
        org.released_modules = sorted(released | {MODULE})
        org.save(update_fields=["released_modules"])


def backward(apps, schema_editor):
    _bypass(schema_editor)
    Organization = apps.get_model("organizations", "Organization")
    for org in Organization.objects.filter(type__in=("federation", "club")):
        changed = []
        for field in ("released_modules", "enabled_modules"):
            values = list(getattr(org, field) or [])
            if MODULE in values:
                setattr(org, field, [v for v in values if v != MODULE])
                changed.append(field)
        if changed:
            org.save(update_fields=changed)


class Migration(migrations.Migration):
    dependencies = [("qualifications", "0001_qualifikationen")]

    operations = [migrations.RunPython(forward, backward)]
