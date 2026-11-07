"""Module „Steuern & Gemeinnützigkeit“ und „Zuwendungsbestätigungen“ (Modulverzeichnis, M2c).

Nichts verschwindet: „tax“ wird eingeschaltet, wo steuerliche Bereiche oder Rücklagen an sind,
„donations“, wo es Einstellungen oder Zuwendungen gibt. Bei einer Untereinheit mit eigener
Kasse gilt das Modul ihres Vereins; dort wird es eingeschaltet.
Rückweg: Beide Module werden wieder entfernt; die Schalter bleiben unverändert.
"""

from django.db import migrations
from django.db.models import Q

NEW = ("tax", "donations")


def _bypass(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def _owner(Organization, org):
    while org is not None and org.type == "unit":
        org = Organization.objects.filter(pk=org.organization_id).first()
    return org


def forward(apps, schema_editor):
    _bypass(schema_editor)
    Organization = apps.get_model("organizations", "Organization")
    DonationSettings = apps.get_model("finance", "DonationSettings")
    Donation = apps.get_model("finance", "Donation")
    wanted: dict[int, set[str]] = {}
    tax_ids = Organization.objects.exclude(type="platform").filter(
        Q(tax_areas_enabled=True) | Q(reserves_enabled=True)
    )
    for org_id in tax_ids.values_list("pk", flat=True):
        wanted.setdefault(org_id, set()).add("tax")
    donation_ids = set(DonationSettings.objects.values_list("organization_id", flat=True))
    donation_ids |= set(Donation.objects.values_list("organization_id", flat=True))
    for org_id in donation_ids:
        wanted.setdefault(org_id, set()).add("donations")
    for org_id, modules in wanted.items():
        target = _owner(Organization, Organization.objects.filter(pk=org_id).first())
        if target is None or target.type == "platform":
            continue
        current = set(target.enabled_modules or [])
        if not modules <= current:
            target.enabled_modules = sorted(current | modules)
            target.save(update_fields=["enabled_modules"])


def backward(apps, schema_editor):
    _bypass(schema_editor)
    Organization = apps.get_model("organizations", "Organization")
    for org in Organization.objects.all():
        current = list(org.enabled_modules or [])
        if any(m in current for m in NEW):
            org.enabled_modules = [m for m in current if m not in NEW]
            org.save(update_fields=["enabled_modules"])


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0053_chronik"),
        ("finance", "0024_gobd_datenbank"),
    ]

    operations = [migrations.RunPython(forward, backward)]
