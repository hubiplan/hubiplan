"""Neue Module (Modulverzeichnis, Schritt M2): Aufgaben, Dokumente, Rundschreiben,
Mitgliedsausweise, Ausschreibungen, Belegung, Mitgliederbereich, Ehrungen & Jubiläen, Würden
und Social Media.

Nichts verschwindet: Aufgaben, Dokumente und Rundschreiben waren immer da und werden überall
eingeschaltet; Ehrungen & Jubiläen, wo Mitglieder an sind; Ausschreibungen, wo Meldungen an
sind; Belegung, wo Material oder Räume an sind; der Mitgliederbereich, wo der Verein ihn
freigeschaltet hat; Ausweise, Würden und Social Media nur dort, wo es schon Daten gibt.
Rückweg: die neuen Kennungen werden wieder entfernt.
"""

from django.db import migrations

NEW = (
    "todos",
    "docs",
    "circulars",
    "cards",
    "calls",
    "bookings",
    "portal",
    "awards",
    "honors",
    "social",
)


def forward(apps, schema_editor):
    from core.tenancy import rls_bypass

    Organization = apps.get_model("organizations", "Organization")
    MemberCard = apps.get_model("cards", "MemberCard")
    Dignity = apps.get_model("honors", "Dignity")
    SocialFeed = apps.get_model("website", "SocialFeed")
    with rls_bypass():
        with_cards = set(MemberCard.objects.values_list("organization_id", flat=True).distinct())
        with_honors = set(Dignity.objects.values_list("organization_id", flat=True).distinct())
        with_social = set(
            SocialFeed.objects.values_list("website__organization_id", flat=True).distinct()
        )
        for org in Organization.objects.exclude(type="platform"):
            modules = set(org.enabled_modules or [])
            before = set(modules)
            if org.type in ("federation", "club"):
                modules |= {"todos", "docs", "circulars"}
                if "entries" in modules:
                    modules.add("calls")
                if modules & {"material", "infrastructure"}:
                    modules.add("bookings")
                if "members" in modules:
                    modules.add("awards")
                    if org.pk in with_cards:
                        modules.add("cards")
                if org.type == "club" and org.member_portal_enabled:
                    modules.add("portal")
                if org.pk in with_honors:
                    modules.add("honors")
            if org.pk in with_social and "website" in modules:
                modules.add("social")
            if modules != before:
                org.enabled_modules = sorted(modules)
                org.save(update_fields=["enabled_modules"])


def backward(apps, schema_editor):
    from core.tenancy import rls_bypass

    Organization = apps.get_model("organizations", "Organization")
    with rls_bypass():
        for org in Organization.objects.all():
            modules = [m for m in org.enabled_modules or [] if m not in NEW]
            if modules != list(org.enabled_modules or []):
                org.enabled_modules = modules
                org.save(update_fields=["enabled_modules"])


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0051_adressen_je_einheit"),
        ("cards", "0003_membercard_wallet_passes"),
        ("honors", "0007_namenskopien_verschluesselt"),
        ("website", "0038_einwilligung_mitgliederliste"),
    ]

    operations = [migrations.RunPython(forward, backward)]
