"""Weitergabe durch den Dachverband und Vorlagen beim Anlegen (Modulverzeichnis, M6).

Erfundene Daten."""

import pytest

from access.modules import TEMPLATES, template_modules

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture
def platform_admin(db, django_user_model):
    return django_user_model.objects.create_superuser(email="admin@example.org", password="x")


def test_dachverband_gibt_nur_mit_weitergabe_frei(orgs, api):
    fed, club = orgs["federation"], orgs["a"]
    club.released_modules = ["members", "events"]
    club.enabled_modules = ["members", "events"]
    club.save()
    user = make_user("bund@example.org")
    give_role(user, fed)
    url = f"/api/orgs/{fed.pk}/clubs/{club.pk}/"
    c = api(user)
    assert c.get(url).json()["released_modules"] == ["events", "members"]
    resp = c.patch(url, {"released_modules": ["members", "events", "todos"]}, JSON)
    assert resp.status_code == 400
    fed.modules_pass_down = True
    fed.save()
    resp = c.patch(url, {"released_modules": ["members", "events", "todos"]}, JSON)
    assert resp.status_code == 200, resp.content
    club.refresh_from_db()
    assert set(club.released_modules) == {"members", "events", "todos"}
    assert "todos" in club.enabled_modules


def test_plattform_schaltet_weitergabe(orgs, platform_admin, api):
    fed = orgs["federation"]
    resp = api(platform_admin).patch(
        f"/api/platform/orgs/{fed.pk}/", {"modules_pass_down": True}, JSON
    )
    assert resp.status_code == 200, resp.content
    fed.refresh_from_db()
    assert fed.modules_pass_down


def test_vorlagen(orgs, api, board_a):
    data = api(board_a).get("/api/modules/templates/").json()
    by_id = {t["id"]: t for t in data}
    assert {"shooting", "competitions", "tax"} <= set(by_id["shooting"]["modules"])
    assert by_id["shooting"]["units"]["label"] == "Zug"
    assert "events" not in by_id["support"]["modules"]
    # Jede Vorlage nennt nur Module, die es für ihre Art von Einheit gibt
    for tpl in TEMPLATES:
        assert template_modules(tpl)


def test_anlegen_mit_vorlage(platform_admin, api):
    tpl = next(t for t in TEMPLATES if t.id == "music")
    resp = api(platform_admin).post(
        "/api/platform/orgs/",
        {
            "name": "Musikverein Musterdorf",
            "founding_year": 1980,
            "street": "Musterweg 1",
            "postal_code": "12345",
            "city": "Musterdorf",
            "keeps_members": True,
            "released_modules": template_modules(tpl),
            "department_label": "Register",
            "department_label_plural": "Register",
            "department_label_gender": "n",
        },
        JSON,
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert {"music", "scores", "events"} <= set(body["enabled_modules"])
    assert body["department_label"] == "Register"
