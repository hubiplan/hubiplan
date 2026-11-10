"""Stilregler der Webseite (Gestaltung › Feinabstimmung, Ralf 10.11.2026, Konzept
webseite-baukasten G1). Alle Daten erfunden."""

import pytest
from django.test import Client

from website import style
from website.models import Website

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db(transaction=True)
KEY = "stil-a"


@pytest.fixture
def club(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "events", "website"]
    org.save()
    return org


@pytest.fixture
def site(club):
    return Website.objects.create(organization=club, public_key=KEY, state="maintenance")


@pytest.fixture
def client_web(club, api):
    user = make_user("web-stil@example.org")
    give_role(user, club, permissions=["website.manage"], name="Webseite")
    return api(user)


def put(c, club, data):
    return c.put(f"/api/orgs/{club.pk}/website/", data, "application/json")


def test_regler_speichern_und_vorgabe(club, site, client_web):
    resp = put(
        client_web,
        club,
        {"style": {"font": "modern", "corners": "round", "sticky": True, "width": None}},
    )
    assert resp.status_code == 200, resp.content
    site.refresh_from_db()
    # „None“ = wie das Design: wird nicht gespeichert
    assert site.style == {"font": "modern", "corners": "round", "sticky": True}
    assert resp.json()["website"]["style"] == site.style


@pytest.mark.parametrize(
    "value",
    [
        {"font": "comic"},
        {"farbe": "rot"},
        {"sticky": "ja"},
        {"corners": ["round"]},
        {"logo": False, "name": False},
        ["font"],
    ],
)
def test_nur_bekannte_stufen(club, site, client_web, value):
    assert put(client_web, club, {"style": value}).status_code == 400
    site.refresh_from_db()
    assert site.style == {}


def test_katalog_fuer_die_oberflaeche(club, site, client_web):
    data = client_web.get(f"/api/orgs/{club.pk}/website/").json()
    catalog = data["style_catalog"]
    assert catalog["options"]["font"] == ["system", "modern", "festive"]
    assert catalog["options"]["sticky"] == "switch"
    assert catalog["locks"]["sidebar"]["logo_pos"] is None
    assert catalog["locks"]["stage"]["width"] == ["narrow"]
    # Jede Leiste hat 2 oder 3 gleich breite Felder (Ralf 10.11.)
    for options in catalog["options"].values():
        assert options == "switch" or 2 <= len(options) <= 3


def test_oeffentliche_schnittstelle(club, site):
    site.state = "public"
    site.save()
    data = Client().get(f"/api/public/site/v1/{KEY}/").json()
    assert data["style"] == {}
    site.style = {"footer": "light", "hero_name": True}
    site.save()
    data = Client().get(f"/api/public/site/v1/{KEY}/").json()
    assert data["style"] == {"footer": "light", "hero_name": True}


def test_alter_ungueltiger_stand_bricht_nichts(club, site):
    site.state = "public"
    site.style = {"font": "comic", "nav": "bar"}
    site.save()
    assert Client().get(f"/api/public/site/v1/{KEY}/").json()["style"] == {}
    assert style.public(None) == {}


def test_gleiche_liste_wie_die_webseite():
    # hubiplan-website/seite/stil.py führt dieselben Regler; hier nur die Form
    assert len(style.OPTIONS) == 29
    for design, locks in style.LOCKS.items():
        for key, values in locks.items():
            assert key in style.OPTIONS, (design, key)
            assert values is None or set(values) <= set(style.OPTIONS[key])
