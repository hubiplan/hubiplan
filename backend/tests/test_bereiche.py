"""Rechte als Bereiche mit drei Stufen: kein Zugriff, lesen, bearbeiten (Ralf 02.11.2026).

Konzept: konzepte/berechtigungen.md. Geprüft werden Katalog, Übergang von den früheren
Codes, die Migration der Rollen und die neuen Leserechte an der Schnittstelle.
"""

from __future__ import annotations

import importlib

import pytest

from access import catalog
from access.catalog import (
    AREAS,
    DEPT_LEGACY_TO_NEW,
    EXTRAS,
    LEGACY_TO_NEW,
    codes_for,
    effective,
    from_legacy,
    normalize,
)
from access.models import Role
from access.permissions import permissions_in

from .factories import give_role, make_user

migration = importlib.import_module("access.migrations.0016_bereiche")

ALT_VEREIN = sorted(LEGACY_TO_NEW)  # alle früheren Codes einer Vereinsrolle


# --- Katalog ---


def test_jeder_bereich_hat_lesen_oder_bearbeiten():
    for area in AREAS:
        assert area.levels, area.id
        for level in area.dept_levels:
            assert level in ("view", "edit")


def test_jeder_fruehere_code_hat_eine_neue_form():
    known = catalog.ALL_CODES
    for old, news in {**LEGACY_TO_NEW, **DEPT_LEGACY_TO_NEW}.items():
        assert news, old
        assert set(news) <= known, old


def test_zusatzrechte_brauchen_einen_bereich_mit_lesen():
    for extra in EXTRAS:
        assert "view" in catalog.AREA_BY_ID[extra.needs].levels


def test_untereinheiten_nutzen_dieselben_bereichsnamen():
    for code in catalog.DEPARTMENT_CODES:
        area = code.rpartition(".")[0]
        assert area in catalog.AREA_BY_ID or code in {e.code for e in EXTRAS}


# --- Übergang ---


def test_bearbeiten_schliesst_lesen_ein():
    assert set(normalize(["finance.edit"])) == {"finance.view", "finance.edit"}
    assert set(normalize(["export.lists"])) == {"export.lists", "members.view"}


def test_fruehere_codes_werden_uebersetzt():
    assert set(normalize(["events.manage", "circulars.send"])) == {
        "events.view",
        "events.edit",
        "circulars.view",
        "circulars.edit",
    }
    assert set(normalize(["dept.members.edit"], dept=True)) == {"members.view", "members.edit"}
    # members.view heißt alt und neu gleich und bleibt allein
    assert normalize(["members.view"]) == ["members.view"]
    # Aus einer alten Datei: Mitglieder lesen hieß auch Fotos und Ausweise sehen
    assert set(from_legacy(["members.view"])) == {
        "members.view",
        "photos.view",
        "cards.view",
        "logins.view",
    }


def test_wirksame_rechte_enthalten_die_frueheren_codes():
    perms = effective(["events.edit", "webcontent.edit", "results.edit"])
    assert {"events.manage", "website.content", "competitions.results"} <= perms
    assert "website.manage" not in perms
    dept = effective(["events.edit", "billing.view"], dept=True)
    assert {"dept.events.manage", "dept.invoices.view"} <= dept


def test_rolle_speichert_die_neue_form(orgs):
    role = Role.objects.create(
        organization=orgs["a"], name="Alt", permissions=["events.manage", "org.edit"]
    )
    role.refresh_from_db()
    assert set(role.permissions) == {"events.view", "events.edit", "settings.view", "settings.edit"}


def test_alle_rechte_einer_art_sind_gueltig(orgs):
    for org_type in ("platform", "federation", "club", "unit"):
        codes = codes_for(org_type)
        assert set(normalize(codes)) == set(codes), org_type


# --- Migration ---


def test_migration_verlustfrei_fuer_alle_frueheren_rechte():
    new = migration.new_codes(ALT_VEREIN, dept=False, org_type="club")
    assert set(migration.old_codes(new, dept=False)) == set(ALT_VEREIN)
    dept_old = sorted(DEPT_LEGACY_TO_NEW)
    dept_new = migration.new_codes(dept_old, dept=True, org_type="club")
    assert set(migration.old_codes(dept_new, dept=True)) == set(dept_old)


def test_migration_gibt_lesen_wo_bisher_jede_rolle_las():
    new = migration.new_codes(["finance.view"], dept=False, org_type="club")
    assert {"settings.view", "theme.view", "events.view", "circulars.view"} <= set(new)
    # Webseite lasen andere Rollen nur technisch: kein Menüpunkt, also kein Leserecht
    assert "website.view" not in new
    assert "webcontent.view" not in new
    dept = migration.new_codes(["dept.invoices.view"], dept=True, org_type="club")
    assert set(dept) == {"billing.view", "events.view", "docs.view"}


def test_migration_laesst_reine_aemter_ohne_rechte():
    assert migration.new_codes([], dept=False, org_type="club") == []
    assert migration.new_codes([], dept=True, org_type="club") == []


def test_migration_stimmt_mit_dem_katalog_ueberein():
    """Die eingefrorene Tabelle der Migration und der Katalog übersetzen gleich."""
    for old in ALT_VEREIN:
        frozen = set(migration.new_codes([old], dept=False, org_type="club"))
        frozen -= set(migration.BASE_READ["club"])
        assert frozen <= set(from_legacy([old])) | set(migration.BASE_READ["club"]), old
        assert set(from_legacy([old])) <= frozen | set(migration.BASE_READ["club"]), old


def test_migration_schreibt_kategorien_der_pruefstellen_mit():
    """Jede frühere Prüfung (alter Code) gilt nach der Migration weiter."""
    for old in ALT_VEREIN:
        new = migration.new_codes([old], dept=False, org_type="club")
        assert old in effective(new), old
    for old in DEPT_LEGACY_TO_NEW:
        new = migration.new_codes([old], dept=True, org_type="club")
        assert old in effective(new, dept=True), old


# --- Schnittstelle ---

pytestmark = pytest.mark.django_db


def _user(org, perms, email="rolle@example.org"):
    if "events" not in (org.enabled_modules or []):
        org.enabled_modules = [*(org.enabled_modules or []), "events"]
        org.save(update_fields=["enabled_modules"])
    user = make_user(email)
    give_role(user, org, perms, name="Testrolle")
    return user


def test_termine_ohne_leserecht_gesperrt(orgs, api):
    org = orgs["a"]
    c = api(_user(org, ["finance.view"]))
    assert c.get(f"/api/orgs/{org.pk}/events/").status_code == 403


def test_termine_lesen_aber_nicht_anlegen(orgs, api):
    org = orgs["a"]
    c = api(_user(org, ["events.view"]))
    assert c.get(f"/api/orgs/{org.pk}/events/").status_code == 200
    created = c.post(
        f"/api/orgs/{org.pk}/events/",
        {"title": "Probe", "starts_at": "2026-11-20T19:00:00+01:00"},
        content_type="application/json",
    )
    assert created.status_code == 403


def test_rollen_nur_lesen(orgs, api):
    org = orgs["a"]
    user = _user(org, ["roles.view"])
    assert "roles.manage" not in permissions_in(user, org)
    c = api(user)
    assert c.get(f"/api/orgs/{org.pk}/roles/").status_code == 200
    assert c.get(f"/api/orgs/{org.pk}/assignments/").status_code == 200
    created = c.post(
        f"/api/orgs/{org.pk}/roles/",
        {"name": "Neu", "permissions": []},
        content_type="application/json",
    )
    assert created.status_code == 403


def test_rollen_ohne_leserecht_gesperrt(orgs, api):
    org = orgs["a"]
    c = api(_user(org, ["members.view"]))
    assert c.get(f"/api/orgs/{org.pk}/roles/").status_code == 403


def test_rollenmaske_nimmt_fruehere_codes_an(orgs, api, board_a):
    org = orgs["a"]
    c = api(board_a)
    created = c.post(
        f"/api/orgs/{org.pk}/roles/",
        {"name": "Alte Oberfläche", "permissions": ["events.manage", "export.run"]},
        content_type="application/json",
    )
    assert created.status_code == 201, created.content
    assert set(created.json()["permissions"]) == {
        "events.view",
        "events.edit",
        "export.lists",
        "members.view",
    }


def test_katalog_liefert_bereiche_mit_stufen(api, board_a):
    data = api(board_a).get("/api/permissions/?org_type=club").json()
    areas = {m["id"]: m for m in data if m["kind"] == "area"}
    assert [lvl["level"] for lvl in areas["members"]["levels"]] == ["view", "edit"]
    assert [lvl["level"] for lvl in areas["audit"]["levels"]] == ["view"]
    extras = next(m for m in data if m["kind"] == "extras")
    assert {p["code"] for p in extras["permissions"]} == {
        "export.lists",
        "export.full",
        "roles.preview",
    }
    dept = api(board_a).get("/api/permissions/?org_type=department").json()
    dept_areas = {m["id"]: m for m in dept if m["kind"] == "area"}
    assert [lvl["level"] for lvl in dept_areas["billing"]["levels"]] == ["view"]
    assert "finance" not in dept_areas


def test_mehrere_rollen_hoechste_stufe(orgs):
    org = orgs["a"]
    user = make_user("zwei@example.org")
    give_role(user, org, ["finance.view"], name="Prüfer")
    give_role(user, org, ["finance.edit"], name="Kassierer")
    perms = permissions_in(user, org)
    assert {"finance.view", "finance.edit"} <= perms


def test_hilfe_nennt_fruehere_codes_mit_neuem_namen(orgs):
    from organizations.help_views import help_state

    rights = help_state(orgs["a"], set())["rights"]
    assert rights["events.manage"] == rights["events.edit"]
    assert rights["org.edit"] == rights["settings.edit"]
    assert rights["competitions.manage"] == rights["competitions.edit"]
    assert rights["website.manage"] == rights["website.edit"]


def test_app_bekommt_neue_codes_aber_nicht_fuer_reines_lesen(orgs):
    from devices.admin_api import admin_units

    org = orgs["a"]
    termine = make_user("termine@example.org")
    give_role(termine, org, ["events.edit"], name="Termine")
    unit = next(u for u in admin_units(termine) if u["id"] == org.pk)
    assert {"events.view", "events.edit", "events.manage"} <= set(unit["permissions"])
    leser = make_user("leser@example.org")
    give_role(leser, org, ["events.view"], name="Leser")
    assert all(u["id"] != org.pk for u in admin_units(leser))
