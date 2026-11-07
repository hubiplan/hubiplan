"""Modulverzeichnis (access/modules.py): einzige Quelle der abschaltbaren Module."""

import pytest

from access import catalog
from access.modules import (
    GROUPS,
    MODULE_BY_ID,
    MODULES,
    with_requirements,
    without_dependents,
)


def test_katalog_liest_verzeichnis():
    assert set(catalog.SWITCHABLE_MODULES) == set(MODULE_BY_ID)
    assert set(catalog.DEFAULT_MODULES) == {m.id for m in MODULES if m.default}
    assert catalog.OPT_IN_MODULES == set(MODULE_BY_ID) - set(catalog.DEFAULT_MODULES)


def test_bereiche_gehoeren_zu_bekannten_modulen():
    for area in catalog.AREAS:
        for module in filter(None, area.module.split("|")):
            assert module in MODULE_BY_ID, (area.id, module)


def test_voraussetzungen_bekannt_und_gruppen_vorhanden():
    groups = {g.id for g in GROUPS}
    for m in MODULES:
        assert m.group in groups
        assert set(m.requires) | set(m.requires_any) <= set(MODULE_BY_ID), m.id


def test_voraussetzungen_einschalten_und_abhaengige_ausschalten():
    assert with_requirements(["music"]) == {"music", "events"}
    assert with_requirements(["meetings", "unbekannt"]) == {"meetings", "events"}
    assert without_dependents(["music", "meetings", "finance"]) == {"finance"}
    assert without_dependents(["music", "events"]) == {"music", "events"}


@pytest.mark.django_db
def test_api_liefert_gruppen(api):
    from .factories import make_user

    client = api(make_user("modul@example.org"))
    data = client.get("/api/modules/").json()
    ids = [m["id"] for g in data for m in g["modules"]]
    assert sorted(ids) == sorted(MODULE_BY_ID)
    music = next(m for g in data for m in g["modules"] if m["id"] == "music")
    assert music["requires"] == ["events"] and music["label"] == "Musik"


def test_aeltere_exportdateien_verlieren_nichts():
    from access.modules import upgrade_modules

    old = upgrade_modules(["members", "entries", "material"], 1, org_type="club")
    assert {"todos", "docs", "circulars", "calls", "bookings"} <= old
    assert "cards" not in old and "honors" not in old
    assert "awards" in old
    assert "honors" in upgrade_modules(["members"], 1, org_type="club", has_honors=True)
    assert "social" in upgrade_modules(["website"], 1, org_type="club", has_social=True)
    assert upgrade_modules(["members"], 2, org_type="club") == {"members"}


@pytest.mark.django_db
def test_abgeschaltetes_modul_nimmt_rechte_und_mitgliederbereich(api):
    from access.permissions import permissions_in
    from core.tenancy import tenant_context
    from portal.models import PortalAccess

    from .factories import give_role, make_member, make_org, make_user

    org = make_org("Verein Modul", member_portal_enabled=True)
    chef = make_user("chef-modul@example.org")
    give_role(chef, org)
    assert {"docs.view", "todos.view", "circulars.view"} <= permissions_in(chef, org)
    user = make_user("mitglied-modul@example.org")
    membership = make_member(org, "Erika", "Modul", user.email)
    with tenant_context(org.pk):
        access = PortalAccess.objects.create(organization=org, membership=membership, user=user)
    member = api(user)
    assert member.get(f"/api/portal/{access.pk}/todos/").status_code == 200

    org.enabled_modules = [m for m in org.enabled_modules if m not in {"docs", "todos"}]
    org.save()
    perms = permissions_in(chef, org)
    assert not {"docs.view", "docs.edit", "todos.view"} & perms
    assert "circulars.view" in perms
    assert member.get(f"/api/portal/{access.pk}/todos/").status_code == 404
    assert member.get(f"/api/portal/{access.pk}/documents/").status_code == 404
    summary = member.get("/api/me/contexts/").json()["portal"][0]
    assert summary["todos_enabled"] is False and summary["circulars_enabled"] is True


@pytest.mark.django_db
def test_ehrungen_wuerden_social_folgen_dem_modul(api):
    from .factories import give_role, make_org, make_user

    org = make_org("Verein Würden")
    chef = make_user("chef-wuerden@example.org")
    give_role(chef, org)
    client = api(chef)
    base = f"/api/orgs/{org.pk}"
    assert client.get(f"{base}/honors/dignities/").status_code == 200
    assert client.get(f"{base}/honorary-titles/").status_code == 200
    assert client.get(f"{base}/jubilees/").status_code == 200

    org.enabled_modules = [m for m in org.enabled_modules if m not in {"honors", "awards"}]
    org.save()
    assert client.get(f"{base}/honors/dignities/").status_code == 404
    assert client.get(f"{base}/honorary-titles/").status_code == 404
    assert client.get(f"{base}/jubilees/").status_code == 404
    # Mitglieder und Webseite ohne Social Media bleiben erreichbar
    assert client.get(f"{base}/members/").status_code == 200
    assert client.get(f"{base}/website/social/").status_code == 404


@pytest.mark.django_db
def test_mitgliederbereich_modul_und_schalter_gleich():
    from organizations.models import Organization

    from .factories import make_org

    org = make_org("Verein Bereich")
    assert "portal" not in org.enabled_modules and not org.member_portal_enabled
    org.member_portal_enabled = True
    org.save(update_fields=["member_portal_enabled"])
    org = Organization.objects.get(pk=org.pk)
    assert "portal" in org.enabled_modules
    org.enabled_modules = [m for m in org.enabled_modules if m != "portal"]
    org.save()
    org = Organization.objects.get(pk=org.pk)
    assert org.member_portal_enabled is False
    neu = make_org("Verein Neu", enabled_modules=["members", "portal"])
    assert neu.member_portal_enabled is True
