"""Titelfoto als Bühne mit Titelzeilen (Webseite #122), Wasserzeichen hinter Abschnitten
(Webseite #123), Terminkarten (#124) und voller Fuß (#125). Alle Daten erfunden."""

import pytest
from django.test import Client

from website import style
from website.home import normalize, skeleton
from website.models import DEFAULT_HOME_OFF, HOME_SECTIONS, Website, WebsiteImage

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db(transaction=True)
KEY = "buehne-a"


@pytest.fixture
def club(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "events", "website"]
    org.save()
    return org


@pytest.fixture
def site(club):
    return Website.objects.create(
        organization=club,
        public_key=KEY,
        state="public",
        privacy_mode="link",
        privacy_url="https://example.org/datenschutz",
    )


@pytest.fixture
def manager(club, api):
    user = make_user("buehne@example.org")
    give_role(user, club, permissions=["website.manage"], name="Webseite")
    return api(user)


def put(manager, club, data):
    return manager.put(f"/api/orgs/{club.pk}/website/", data, "application/json")


def public():
    return Client().get(f"/api/public/site/v1/{KEY}/").json()


def by_key(sections):
    return {s["key"]: s for s in sections}


def test_neue_regler():
    assert style.OPTIONS["hero_width"] == ("content", "stage", "full")
    assert style.OPTIONS["footer_layout"] == ("simple", "full")
    assert style.OPTIONS["footer_line"] == ("none", "ornament", "accent", "primary")
    assert "card" in style.OPTIONS["date"]
    assert style.LOCKS["stage"]["hero_width"] is None
    assert style.validate({"hero_width": "full", "date": "card", "footer_layout": "full"}) == {
        "date": "card",
        "hero_width": "full",
        "footer_layout": "full",
    }
    with pytest.raises(ValueError):
        style.validate({"footer_line": "gold"})


def test_buehne_in_inhaltsbreite_und_fuss_ohne_name():
    """Webseite #127/#128: Stufe „stage“, Fläche daneben, Name/Gründung im Fuß ausblendbar."""
    assert style.OPTIONS["hero_width"] == ("content", "stage", "full")
    assert style.OPTIONS["hero_side"] == ("page", "color")
    assert style.OPTIONS["hero_stage_width"] == ("content", "wider", "wide")
    assert style.LOCKS["stage"]["hero_stage_width"] is None
    assert style.OPTIONS["footer_name"] is bool and style.OPTIONS["footer_founded"] is bool
    assert style.LOCKS["stage"]["hero_side"] is None
    assert style.LOCKS["newspaper"]["hero_side"] is None
    werte = {
        "hero_width": "stage",
        "hero_side": "color",
        "hero_stage_width": "wider",
        "footer_name": False,
        "footer_founded": False,
    }
    assert style.validate(werte) == werte
    assert style.defaults("classic")["footer_name"] is True
    assert style.defaults("classic")["hero_side"] == "page"
    with pytest.raises(ValueError):
        style.validate({"footer_name": "nein"})
    with pytest.raises(ValueError):
        style.validate({"hero_side": "gold"})


def test_titelzeilen_werden_bereinigt():
    out = by_key(
        normalize(
            [
                {
                    "key": "carousel",
                    "on": True,
                    "title": "  Tradition,   die verbindet.\n\nSeit 1920 zu Hause.\n" + "x" * 200,
                    "kicker": "Schützenverein   Musterstadt",
                },
                {"key": "greeting", "on": True, "title": "nicht hier"},
            ],
            HOME_SECTIONS,
            DEFAULT_HOME_OFF,
        )
    )
    assert (
        out["carousel"]["title"] == "Tradition, die verbindet.\nSeit 1920 zu Hause.\n" + "x" * 120
    )
    assert out["carousel"]["kicker"] == "Schützenverein Musterstadt"
    assert "title" not in out["greeting"]
    many = "\n".join(f"Zeile {i}" for i in range(9))
    out = normalize([{"key": "carousel", "on": True, "title": many}], HOME_SECTIONS, set())
    assert out[0]["title"].count("\n") == 5


def test_titelzeilen_speichern_und_ausliefern(club, site, manager):
    resp = put(
        manager,
        club,
        {
            "home_sections": [
                {
                    "key": "carousel",
                    "on": True,
                    "title": "Willkommen in Musterstadt.\nTradition, die verbindet.",
                    "kicker": "Seit 1920",
                }
            ],
            "style": {"hero_width": "full"},
        },
    )
    assert resp.status_code == 200, resp.content
    data = public()
    assert data["style"]["hero_width"] == "full"
    entry = next(s for s in data["home_layout"] if s["key"] == "carousel")
    assert entry["hero_titles"] == ["Willkommen in Musterstadt.", "Tradition, die verbindet."]
    assert entry["hero_kicker"] == "Seit 1920"


def test_zu_viele_oder_zu_lange_titelzeilen(club, site, manager):
    seven = "\n".join(f"Zeile {i}" for i in range(7))
    for title in (seven, "x" * 121, 5):
        resp = put(
            manager, club, {"home_sections": [{"key": "carousel", "on": True, "title": title}]}
        )
        assert resp.status_code == 400, title


def test_wasserzeichen_wappen_und_bild(club, site, manager):
    hirsch = WebsiteImage.objects.create(
        organization=club, website=site, key="hirsch", alt_text="Hirsch"
    )
    resp = put(
        manager,
        club,
        {
            "home_sections": [
                {"key": "greeting", "on": True, "bg": "p0", "width": "full", "mark": "logo"},
                {
                    "key": "c:kasten",
                    "kind": "text",
                    "on": True,
                    "bg": "light",
                    "mark": hirsch.pk,
                    "data": {"title": "Über uns", "text": "Ein erfundener Verein."},
                },
                {"key": "events", "on": True, "mark": "kaputt"},
            ]
        },
    )
    assert resp.status_code == 200, resp.content
    saved = by_key(resp.json()["website"]["home_sections"])
    assert saved["greeting"]["mark"] == "logo"
    assert saved["c:kasten"]["mark"] == hirsch.pk
    assert "mark" not in saved["events"]
    layout = by_key(public()["home_layout"])
    assert layout["greeting"]["mark"] == "logo"
    assert isinstance(layout["c:kasten"]["mark"], dict)
    # Das Bild darf öffentlich ausgeliefert werden, weil ein eingeschalteter Abschnitt es nutzt
    from website.public import SiteView

    site.refresh_from_db()
    assert hirsch.pk in SiteView(site).home_image_ids


def test_wasserzeichen_unbekanntes_bild_faellt_weg(club, site, manager):
    resp = put(
        manager,
        club,
        {"home_sections": [{"key": "greeting", "on": True, "bg": "light", "mark": 987654}]},
    )
    assert resp.status_code == 200, resp.content
    assert "mark" not in by_key(resp.json()["website"]["home_sections"])["greeting"]


def test_wasserzeichen_gehoert_zum_aussehen():
    plain = [{"key": "greeting", "on": True, "bg": "light"}]
    marked = [{"key": "greeting", "on": True, "bg": "light", "mark": "logo"}]
    assert skeleton(plain) != skeleton(marked)
