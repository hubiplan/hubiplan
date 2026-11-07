"""Modul „Schießsport“: Scheiben, Fotoauswertung und Vogelschießen (Modulverzeichnis, M2c).

Erfundene Daten."""

import pytest

from access.modules import upgrade_modules, with_requirements

pytestmark = pytest.mark.django_db
JSON = "application/json"


def url(org, rest=""):
    return f"/api/orgs/{org.pk}/competitions/{rest}"


def _modules(org, *modules):
    org.refresh_from_db()
    org.enabled_modules = ["members", "competitions", *modules]
    org.save()


def _ranking(c, org):
    resp = c.post(
        url(org),
        {"title": "Preisschießen", "date": "2027-06-14", "template": "einfach"},
        JSON,
    )
    assert resp.status_code == 201, resp.content
    comp_id = resp.json()["id"]
    scoring = c.get(url(org, f"{comp_id}/")).json()["scorings"][0]["id"]
    return comp_id, scoring


def test_ohne_schiesssport_keine_scheiben_und_kein_vogelschiessen(orgs, board_a, api):
    org = orgs["a"]
    _modules(org)
    c = api(board_a)
    bird = {"title": "Vogelschießen", "date": "2027-06-13", "template": "vogel"}
    assert c.post(url(org), bird, JSON).status_code == 400
    assert c.post(url(org), {**bird, "template": "", "form": "vogel"}, JSON).status_code == 400
    comp_id, scoring = _ranking(c, org)
    resp = c.patch(url(org, f"{comp_id}/scorings/{scoring}/"), {"target": "lg10_dsb"}, JSON)
    assert resp.status_code == 400
    assert c.get(url(org, "targets/")).status_code == 404
    assert c.get(url(org, "photo-samples/")).status_code == 404
    assert c.get(url(org, f"{comp_id}/hits/")).status_code == 404
    # Ranglisten ohne Scheibe gehen weiter
    assert c.get(url(org, f"{comp_id}/standings/")).status_code == 200


def test_mit_schiesssport(orgs, board_a, api):
    org = orgs["a"]
    _modules(org, "shooting")
    c = api(board_a)
    comp_id, scoring = _ranking(c, org)
    resp = c.patch(url(org, f"{comp_id}/scorings/{scoring}/"), {"target": "lg10_dsb"}, JSON)
    assert resp.status_code == 200, resp.content
    assert c.get(url(org, "targets/")).status_code == 200
    bird = {"title": "Vogelschießen", "date": "2027-06-13", "template": "vogel"}
    resp = c.post(url(org), bird, JSON)
    assert resp.status_code == 201, resp.content
    bird_id = resp.json()["id"]
    assert c.get(url(org, f"{bird_id}/bird/")).status_code == 200
    # Abgeschaltet: Vogelschießen ruht, die Scheibe der Wertung bleibt gespeichert
    _modules(org)
    assert c.get(url(org, f"{bird_id}/bird/")).status_code == 404
    data = c.get(url(org, f"{comp_id}/")).json()
    assert data["scorings"][0]["target"] == "lg10_dsb"


def test_schiesssport_setzt_wettbewerbe_voraus():
    assert with_requirements(["shooting"]) == {"shooting", "competitions"}


def test_aeltere_exportdatei_behaelt_schiesssport():
    assert "shooting" in upgrade_modules(["competitions"], 5)
    assert upgrade_modules(["competitions"], 6) == {"competitions"}
