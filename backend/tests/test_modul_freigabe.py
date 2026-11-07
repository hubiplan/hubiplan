"""Freigabe durch die Plattform und Einschalten durch die Einheit (Modulverzeichnis, M3).

Erfundene Daten."""

import pytest

from access.modules import apply_enabled, apply_release, released_of

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture
def platform_admin(db, django_user_model):
    return django_user_model.objects.create_superuser(email="admin@example.org", password="x")


def _state(data):
    return {m["id"]: m for g in data["groups"] for m in g["modules"]}


def test_verein_schaltet_innerhalb_der_freigabe(orgs, board_a, api):
    org = orgs["a"]
    org.released_modules = ["members", "events", "music", "scores", "todos"]
    org.enabled_modules = ["members", "events", "todos"]
    org.save()
    c = api(board_a)
    base = f"/api/orgs/{org.pk}/modules/"
    state = _state(c.get(base).json())
    assert state["music"]["released"] and not state["music"]["enabled"]
    assert not state["website"]["released"]
    # Musik nimmt das Notenarchiv mit
    resp = c.patch(base, {"enabled": ["members", "events", "todos", "music"]}, JSON)
    assert resp.status_code == 200, resp.content
    assert resp.json()["changes"]["on"] == ["music", "scores"]
    org.refresh_from_db()
    assert {"music", "scores"} <= set(org.enabled_modules)
    # Nicht freigegeben geht nicht
    resp = c.patch(base, {"enabled": ["members", "website"]}, JSON)
    assert resp.status_code == 400
    # Probelauf: Termine aus nimmt Musik mit, ohne zu speichern
    wanted = ["members", "todos", "music", "scores"]
    resp = c.patch(base, {"enabled": wanted, "dry_run": True}, JSON)
    assert resp.json()["changes"]["off"] == ["events", "music"]
    org.refresh_from_db()
    assert "events" in org.enabled_modules


def test_nur_mit_einstellungsrecht(orgs, api):
    org = orgs["a"]
    user = make_user("leser@example.org")
    give_role(user, org, permissions=["settings.view"], name="Einstellungen lesen")
    c = api(user)
    base = f"/api/orgs/{org.pk}/modules/"
    assert c.get(base).status_code == 200
    assert c.patch(base, {"enabled": ["members"]}, JSON).status_code == 403


def test_plattform_gibt_frei_und_entzieht(orgs, platform_admin, api):
    org = orgs["a"]
    org.released_modules = ["members", "events"]
    org.enabled_modules = ["members"]
    org.save()
    c = api(platform_admin)
    resp = c.patch(
        f"/api/platform/orgs/{org.pk}/",
        {"released_modules": ["members", "events", "todos"]},
        JSON,
    )
    assert resp.status_code == 200, resp.content
    org.refresh_from_db()
    # Neu freigegeben wird eingeschaltet; was der Verein ausgeschaltet hat, bleibt aus
    assert set(org.enabled_modules) == {"members", "todos"}
    assert resp.json()["released_modules"] == ["events", "members", "todos"]
    # Ältere Aufrufe mit enabled_modules gelten als Freigabe
    resp = c.patch(f"/api/platform/orgs/{org.pk}/", {"enabled_modules": ["members"]}, JSON)
    assert resp.status_code == 200, resp.content
    org.refresh_from_db()
    assert org.enabled_modules == ["members"] and org.released_modules == ["members"]


def test_hilfsfunktionen(orgs):
    org = orgs["a"]
    org.released_modules = []
    org.enabled_modules = ["members", "events"]
    assert released_of(org) == {"members", "events"}  # ältere Stände
    apply_release(org, ["members", "events", "meetings"])
    assert set(org.enabled_modules) == {"members", "events", "meetings"}
    apply_release(org, ["members", "meetings"])  # Termine weg, Versammlungen brauchen sie
    assert set(org.released_modules) == {"members", "meetings", "events"}
    added, removed = apply_enabled(org, ["members"])
    assert set(org.enabled_modules) == {"members"} and not added and not removed
