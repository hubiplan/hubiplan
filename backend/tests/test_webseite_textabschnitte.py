"""Textseiten aus Abschnitten (Konzept webseite-baukasten G4, Ralf 10.11.2026).
Alle Daten erfunden."""

import pytest
from django.test import Client

from website import content
from website.models import Website, WebsiteImage, WebsiteText

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db(transaction=True)
KEY = "textabschnitte-a"


@pytest.fixture
def site(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "events", "website"]
    org.save()
    return Website.objects.create(
        organization=org,
        public_key=KEY,
        state="public",
        privacy_mode="link",
        privacy_url="https://example.org/datenschutz",
    )


@pytest.fixture
def editor(orgs):
    user = make_user("text-abschnitte@example.org")
    give_role(user, orgs["a"], permissions=["website.content"], name="Schriftführer")
    return user


def url(org, rest=""):
    return f"/api/orgs/{org.pk}/website/{rest}"


def page(slug):
    return Client().get(f"/api/public/site/v1/{KEY}/pages/{slug}/")


def new_page(c, org, **extra):
    resp = c.post(
        url(org, "texts/"),
        {"kind": "page", "slug": "verein", "title": "Verein", "body": "Seit 1920.", **extra},
        "application/json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()["id"]


def test_ohne_abschnitte_wie_bisher(orgs, editor, api, site):
    c = api(editor)
    pk = new_page(c, orgs["a"])
    data = c.get(url(orgs["a"], f"texts/{pk}/")).json()
    # Der bisherige Text ist der feste erste Abschnitt
    assert [s["key"] for s in data["sections"]] == ["body"]
    c.post(url(orgs["a"], f"texts/{pk}/publish/"))
    out = page("verein").json()
    assert out["text"] and [s["kind"] for s in out["sections"]] == ["body"]


def test_abschnitte_mit_entwurf_und_fassung(orgs, editor, api, site):
    c = api(editor)
    image = WebsiteImage.objects.create(
        organization=orgs["a"], website=site, key="vereinsbild", alt_text="Fahne"
    )
    pk = new_page(c, orgs["a"])
    c.post(url(orgs["a"], f"texts/{pk}/publish/"))
    sections = [
        {
            "key": "c:z1",
            "kind": "quote",
            "on": True,
            "data": {"text": "Einigkeit macht stark."},
        },
        {"key": "body", "on": True, "width": "text"},
        {
            "key": "c:b1",
            "kind": "banner",
            "on": True,
            "bg": "light",
            "data": {"image": image.pk, "line": "Festzug"},
        },
    ]
    resp = c.put(url(orgs["a"], f"texts/{pk}/"), {"sections": sections}, "application/json")
    assert resp.status_code == 200, resp.content
    assert resp.json()["has_changes"] is True
    # Veröffentlicht bleibt der alte Stand
    assert [s["kind"] for s in page("verein").json()["sections"]] == ["body"]
    c.post(url(orgs["a"], f"texts/{pk}/publish/"))
    out = page("verein").json()["sections"]
    assert [s["kind"] for s in out] == ["quote", "body", "banner"]
    assert out[1]["width"] == "text" and out[2]["bg"] == "light"
    assert out[2]["image"]["url"]
    # Bild des Abschnitts ist öffentlich und gilt als verwendet
    from website.public import SiteView

    assert SiteView(site).public_image("vereinsbild") is not None
    assert image.pk in content.used_image_ids(site)
    assert any("Abschnitt" in p for p in content.image_in_use(image))
    # Fassung zurückholen bringt die Abschnitte als Entwurf zurück
    text = WebsiteText.objects.get(pk=pk)
    first = text.revisions.order_by("published_at", "pk").first()
    data = c.post(url(orgs["a"], f"texts/{pk}/revisions/{first.pk}/restore/")).json()
    assert [s["key"] for s in data["sections"]] == ["body"]


def test_abschnitte_nur_auf_textseiten(orgs, editor, api, site):
    c = api(editor)
    texts = c.get(url(orgs["a"], "texts/")).json()["texts"]
    greeting = next(t for t in texts if t["kind"] == "greeting")
    resp = c.put(
        url(orgs["a"], f"texts/{greeting['id']}/"),
        {"sections": [{"key": "c:t1", "kind": "text", "on": True, "data": {"title": "X"}}]},
        "application/json",
    )
    assert resp.status_code == 400


def test_abschnitte_werden_geprueft(orgs, editor, api, site):
    c = api(editor)
    pk = new_page(c, orgs["a"])
    bad = [{"key": "c:t1", "kind": "gibtsnicht", "on": True, "data": {}}]
    resp = c.put(url(orgs["a"], f"texts/{pk}/"), {"sections": bad}, "application/json")
    assert resp.status_code == 400
    # Feste Bausteine der Startseite gibt es auf Textseiten nicht
    bad = [{"key": "honors", "on": True}]
    resp = c.put(url(orgs["a"], f"texts/{pk}/"), {"sections": bad}, "application/json")
    assert resp.status_code == 400


def test_umzug_stellt_nummern_um():
    from website.home import remap

    sections = [
        {"key": "body", "on": True},
        {
            "key": "c:k1",
            "kind": "tiles",
            "on": True,
            "data": {
                "tiles": [{"title": "A", "image": 5, "target": {"event": 7}}],
                "roles": [3, 4],
            },
        },
        {"key": "c:b1", "kind": "banner", "on": True, "data": {"image": 9}},
    ]
    maps = {"website.websiteimage": {5: 50}, "events.event": {7: 70}, "access.role": {3: 30}}
    out = remap(sections, lambda table, old: maps.get(table, {}).get(old))
    assert out[1]["data"]["tiles"][0] == {"title": "A", "image": 50, "target": {"event": 70}}
    assert out[1]["data"]["roles"] == [30]
    assert out[2]["data"]["image"] is None


def test_auswahl_fuer_abschnitte(orgs, editor, api, site):
    data = api(editor).get(url(orgs["a"], "texts/")).json()
    options = data["section_options"]
    assert "banner" in options["home_kinds"]
    assert options["home_labels"] == {"body": "Text der Seite"}
    assert set(options["home_choices"]) == {
        "roles",
        "albums",
        "events",
        "places",
        "categories",
        "documents",
    }
    assert isinstance(options["blocks"], dict) and "menu_items" in options
