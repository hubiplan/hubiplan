"""Modul „Notenarchiv“: Notenbestand auch ohne Musik, eigene Rechte (Modulverzeichnis, M2c).

Erfundene Daten."""

import pytest

from access.catalog import catalog_for
from access.modules import upgrade_modules, with_requirements

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


def _modules(org, *modules):
    org.refresh_from_db()
    org.enabled_modules = ["members", *modules]
    org.save()


def test_chor_ohne_musik_pflegt_noten(orgs, api):
    org = orgs["a"]
    _modules(org, "scores")
    user = make_user("notenwart@example.org")
    give_role(user, org, permissions=["scores.edit"], name="Notenwart")
    c = api(user)
    base = f"/api/orgs/{org.pk}/music"
    piece = c.post(f"{base}/pieces/", {"title": "Musterlied"}, content_type=JSON)
    assert piece.status_code == 201, piece.content
    assert [p["title"] for p in c.get(f"{base}/pieces/").json()] == ["Musterlied"]
    assert c.get(f"{base}/catalogue-import/").status_code == 200
    # Auftritte gehören weiter zu Musik
    assert c.get(f"{base}/performances/").status_code in (403, 404)


def test_musik_rollen_lesen_den_bestand_schreiben_aber_nicht(orgs, api):
    org = orgs["a"]
    _modules(org, "events", "music", "scores")
    user = make_user("musiker@example.org")
    give_role(user, org, permissions=["music.edit"], name="Musikleitung")
    c = api(user)
    base = f"/api/orgs/{org.pk}/music"
    assert c.get(f"{base}/arrangements/").status_code == 200
    assert c.post(f"{base}/pieces/", {"title": "Neu"}, content_type=JSON).status_code == 403


def test_ohne_notenarchiv_kein_bestand(orgs, board_a, api):
    org = orgs["a"]
    _modules(org)
    c = api(board_a)
    base = f"/api/orgs/{org.pk}/music"
    assert c.get(f"{base}/pieces/").status_code == 404
    assert c.get(f"{base}/catalogue-import/").status_code == 404
    assert "scores" not in {a["id"] for a in catalog_for("club", org)}


def test_musik_setzt_das_notenarchiv_voraus():
    assert "scores" in with_requirements(["music"])
    assert with_requirements(["scores"]) == {"scores"}


def test_aeltere_exportdatei_behaelt_den_notenbestand():
    assert "scores" in upgrade_modules(["events", "music"], 4)
    assert "scores" not in upgrade_modules(["events"], 4)
    assert upgrade_modules(["events", "music"], 5) == {"events", "music"}
