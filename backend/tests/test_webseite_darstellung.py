"""Darstellung der festen Bereiche und Einleitungstexte (Konzept webseite-baukasten G5,
Ralf 10.11.2026). Alle Daten erfunden."""

import pytest
from django.test import Client

from website import services
from website.models import Website, WebsiteImage, WebsiteText

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db(transaction=True)
KEY = "darstellung-a"
STANDARD = {"board": "cards", "events": "list", "units": "large", "gallery": "tiles"}


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
    user = make_user("darstellung@example.org")
    give_role(user, club, permissions=["website.manage"], name="Webseite")
    return api(user)


@pytest.fixture
def editor(club, api):
    user = make_user("einleitung@example.org")
    give_role(user, club, permissions=["website.content"], name="Schriftführer")
    return api(user)


def url(club, path=""):
    return f"/api/orgs/{club.pk}/website/{path}"


def public(site, preview=False):
    headers = {}
    if preview:
        session, _ = services.exchange(site, services.open_token(site))
        headers = {"HTTP_X_PREVIEW_SESSION": session}
    return Client().get(f"/api/public/site/v1/{KEY}/", **headers).json()


def test_standard_wie_bisher(club, site, manager):
    assert public(site)["layouts"] == STANDARD and public(site)["intros"] == {}
    data = manager.get(url(club)).json()
    assert [c["area"] for c in data["layout_catalog"]] == list(STANDARD)
    assert data["website"]["layouts"] == {}


def test_darstellung_im_entwurf(club, site, manager):
    draft = {"layouts": {"events": "calendar", "units": "list", "board": "cards"}}
    resp = manager.put(url(club), {"draft": draft}, "application/json")
    assert resp.status_code == 200, resp.content
    # Standardvarianten werden nicht gespeichert
    assert resp.json()["website"]["draft"] == {"layouts": {"events": "calendar", "units": "list"}}
    assert public(site)["layouts"]["events"] == "list"
    assert public(site, preview=True)["layouts"]["events"] == "calendar"
    manager.post(url(club, "design/publish/"))
    site.refresh_from_db()
    assert site.layouts == {"events": "calendar", "units": "list"}
    assert public(site)["layouts"] == {**STANDARD, "events": "calendar", "units": "list"}


@pytest.mark.parametrize(
    "layouts", [{"events": "poster"}, {"honors": "list"}, ["events"], {"board": None}]
)
def test_darstellung_wird_geprueft(club, site, manager, layouts):
    resp = manager.put(url(club), {"draft": {"layouts": layouts}}, "application/json")
    assert resp.status_code == 400


def test_einleitung_je_bereich(club, site, editor):
    areas = editor.get(url(club, "texts/")).json()["intro_areas"]
    assert [a["area"] for a in areas] == list(STANDARD)
    image = WebsiteImage.objects.create(
        organization=club, website=site, key="vorstandsbild", alt_text="Vorstand"
    )
    resp = editor.post(
        url(club, "texts/"),
        {"kind": "intro", "slug": "board", "body": "Unser Vorstand **2099**.", "image": image.pk},
        "application/json",
    )
    assert resp.status_code == 201, resp.content
    pk = resp.json()["id"]
    assert resp.json()["area_label"] == "Vorstand"
    # Je Bereich nur eine Einleitung, nur bekannte Bereiche
    again = editor.post(url(club, "texts/"), {"kind": "intro", "slug": "board"}, "application/json")
    assert again.status_code == 400
    bad = editor.post(url(club, "texts/"), {"kind": "intro", "slug": "honors"}, "application/json")
    assert bad.status_code == 400
    # Erst nach dem Veröffentlichen öffentlich; kein Menüpunkt, keine Textseite
    assert public(site)["intros"] == {}
    editor.post(url(club, f"texts/{pk}/publish/"))
    intro = public(site)["intros"]["board"]
    assert "**2099**" in intro["text"] and intro["image"]["url"]
    assert Client().get(f"/api/public/site/v1/{KEY}/pages/board/").status_code == 404
    assert not any(i.get("key") == "page:board" for i in public(site).get("nav", []))
    from website.public import SiteView

    assert SiteView(site).public_image("vorstandsbild") is not None
    assert WebsiteText.objects.get(pk=pk).kind == "intro"
