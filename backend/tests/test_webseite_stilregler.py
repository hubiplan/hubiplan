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
    # Jede Leiste hat 2 oder 3 gleich breite Felder (Ralf 10.11.);
    # Ausnahmen: Kopfhöhe und Titelbild mit vier Stufen (Ralf 13.11., Webseite #68)
    for key, options in catalog["options"].items():
        most = 4 if key in ("header_height", "hero") else 3
        assert options == "switch" or 2 <= len(options) <= most


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
    assert len(style.OPTIONS) == 48
    for design, locks in style.LOCKS.items():
        for key, values in locks.items():
            assert key in style.OPTIONS, (design, key)
            assert values is None or set(values) <= set(style.OPTIONS[key])


def test_kopfhoehe_mittel(club, site, client_web):
    """Zwischenstufe „mittel“ zwischen niedrig und normal (Webseite #68)."""
    assert style.OPTIONS["header_height"] == ("low", "medium", "normal", "high")
    resp = put(client_web, club, {"style": {"header_height": "medium"}})
    assert resp.status_code == 200, resp.content
    site.refresh_from_db()
    assert site.style == {"header_height": "medium"}


def test_neue_regler(club, site, client_web):
    """Ralf 13.11.: Titelbild „mittel“, Schrift „sehr groß“, Kontrast, Handymenü, Bildformat
    der Kacheln, Karussell, „Nach oben“ und die dunkle Darstellung."""
    values = {
        "hero": "medium",
        "size": "xlarge",
        "contrast": True,
        "nav_mobile": "scroll",
        "tile_ratio": "square",
        "carousel": "slow",
        "to_top": True,
        "dark": "auto",
    }
    resp = put(client_web, club, {"style": values})
    assert resp.status_code == 200, resp.content
    site.refresh_from_db()
    assert site.style == values
    assert put(client_web, club, {"style": {"carousel": "fast"}}).status_code == 400
    assert put(client_web, club, {"style": {"contrast": "on"}}).status_code == 400
    assert style.LOCKS["sidebar"]["nav_mobile"] is None


def test_regler_vom_14_11(club, site, client_web):
    """Ralf 14.11.: Titelbild abdunkeln/färben, Ausschnitt, Lage des Namens, Trenner,
    Unterseitenkopf, Schrift der Überschriften, Menüschrift, Einblenden, Tabellen, Datum."""
    values = {
        "hero_shade": "strong",
        "hero_tint": "accent",
        "hero_focus": "bottom",
        "hero_text": "center",
        "sections": "alternate",
        "page_title": "image",
        "heading_font": "modern",
        "nav_case": "upper",
        "nav_size": "large",
        "motion": "subtle",
        "stripes": True,
        "date_text": "short",
    }
    resp = put(client_web, club, {"style": values})
    assert resp.status_code == 200, resp.content
    site.refresh_from_db()
    assert site.style == values
    assert put(client_web, club, {"style": {"hero_tint": "rot"}}).status_code == 400
    assert put(client_web, club, {"style": {"stripes": "ja"}}).status_code == 400


def test_vorgaben_je_design():
    """Die Oberfläche markiert die Stufe, die das Design zeigt; nur gültige Stufen."""
    from website.designs import DESIGNS

    for design in DESIGNS:
        given = style.defaults(design)
        assert given, design
        for key, value in given.items():
            allowed = style.OPTIONS[key]
            if allowed is bool:
                assert isinstance(value, bool), (design, key)
            else:
                assert value in allowed, (design, key, value)
    assert style.defaults("classic")["nav"] == "buttons"
    assert style.defaults("stage")["sticky"] is True
    # Ecken mit 10 px liegen zwischen den Stufen: keine Markierung
    assert "corners" not in style.defaults("classic")
    assert style.defaults("festive")["corners"] == "slight"
    assert style.defaults("paket-unbekannt") == {}


def test_voreinstellungen_sind_gueltig(club, site, client_web):
    assert set(style.PRESETS) == {"calm", "festive", "modern", "readable"}
    for name, values in style.PRESETS.items():
        assert style.validate(values) == {k: values[k] for k in style.OPTIONS if k in values}, name
    resp = put(client_web, club, {"style": style.PRESETS["festive"]})
    assert resp.status_code == 200, resp.content


def test_katalog_mit_vorgaben_und_voreinstellungen(club, site, client_web):
    resp = client_web.get(f"/api/orgs/{club.pk}/website/")
    cat = resp.json()["style_catalog"]
    assert cat["defaults"]["classic"]["header_bg"] == "white"
    assert cat["presets"]["readable"]["size"] == "large"
