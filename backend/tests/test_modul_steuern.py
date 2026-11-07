"""Module „Steuern & Gemeinnützigkeit“ und „Zuwendungsbestätigungen“ (Modulverzeichnis, M2c).

Erfundene Daten."""

import pytest

from access.modules import upgrade_modules, with_requirements
from organizations.models import Department

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


def _summary(c, org):
    return next(o for o in c.get("/api/me/organizations/").json() if o["id"] == org.pk)


def _switch(org, *modules):
    org.refresh_from_db()
    org.enabled_modules = ["finance", "members", *modules]
    org.save()


def test_ohne_modul_keine_ruecklagen_und_keine_steuerlichen_bereiche(orgs, board_a, api):
    org = orgs["a"]
    _switch(org, "tax")
    c = api(board_a)
    fin = f"/api/orgs/{org.pk}/finance"
    assert c.patch(f"{fin}/settings/", {"reserves_enabled": True}, JSON).status_code == 200
    data = c.patch(f"{fin}/settings/", {"tax_areas_enabled": True}, JSON).json()
    assert data["tax_areas_enabled"] is True and data["reserves_enabled"] is True
    assert c.get(f"{fin}/reserves/").status_code == 200
    assert _summary(c, org)["reserves_enabled"] is True

    _switch(org)
    data = c.get(f"{fin}/settings/").json()
    # Die Schalter bleiben gespeichert, wirken aber erst wieder mit dem Modul
    org.refresh_from_db()
    assert org.tax_areas_enabled and org.reserves_enabled
    assert data["tax_areas_enabled"] is False and data["reserves_enabled"] is False
    assert c.get(f"{fin}/reserves/").status_code == 404
    assert c.patch(f"{fin}/settings/", {"reserves_enabled": False}, JSON).status_code == 404
    assert c.patch(f"{fin}/settings/", {"tax_areas_enabled": False}, JSON).status_code == 404
    assert _summary(c, org)["reserves_enabled"] is False
    # Andere Einstellungen der Kasse gehen weiter
    resp = c.patch(f"{fin}/settings/", {"cash_counts_enabled": True}, JSON)
    assert resp.status_code == 200


def test_zuwendungen_nur_mit_modul(orgs, board_a, api):
    org = orgs["a"]
    _switch(org)
    c = api(board_a)
    fin = f"/api/orgs/{org.pk}/finance"
    assert c.get(f"{fin}/donations/").status_code == 404
    assert c.get(f"{fin}/donation-settings/").status_code == 404
    _switch(org, "donations")
    assert c.get(f"{fin}/donations/").status_code == 200
    assert c.get(f"{fin}/donation-settings/").status_code == 200


def test_untereinheit_mit_eigener_kasse_erbt_vom_verein(orgs, api):
    club = orgs["a"]
    _switch(club, "tax", "donations")
    unit = Department.objects.create(organization=club, name="Zug 1", own_workspace=True)
    unit.enabled_modules = ["finance"]
    unit.save()
    user = make_user("kasse-zug@example.org")
    give_role(user, unit, permissions=["finance.view", "finance.edit"], name="Kasse")
    c = api(user)
    assert {"tax", "donations"} <= set(_summary(c, unit)["modules"])
    assert c.get(f"/api/orgs/{unit.pk}/finance/donations/").status_code == 200
    _switch(club)
    assert not {"tax", "donations"} & set(_summary(c, unit)["modules"])
    assert c.get(f"/api/orgs/{unit.pk}/finance/donations/").status_code == 404


def test_module_setzen_die_kasse_voraus():
    assert with_requirements(["tax"]) == {"tax", "finance"}
    assert with_requirements(["donations"]) == {"donations", "finance"}


def test_aeltere_exportdatei_behaelt_steuern_und_zuwendungen():
    old = ["members", "finance"]
    up = upgrade_modules(old, 3, has_tax=True, has_donations=True)
    assert {"tax", "donations"} <= up
    assert not {"tax", "donations"} & upgrade_modules(old, 3)
    assert not {"tax", "donations"} & upgrade_modules(["members"], 3, has_tax=True)
    assert upgrade_modules(old, 4, has_tax=True) == set(old)
