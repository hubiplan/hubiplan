"""Seiten der Untereinheiten aus Abschnitten (#491): feste Blöcke der Untereinheit, eigene
Abschnitte davor und danach, Bildplatz ohne Bild im Entwurf. Alle Daten erfunden."""

import pytest
from django.test import Client

from organizations.models import Department
from website import search
from website.home import UNIT_BUILTINS
from website.models import WebsiteText
from website.public import SiteView

from .factories import give_role, make_user, make_website

pytestmark = pytest.mark.django_db(transaction=True)
KEY = "untereinheit-abschnitte-a"


@pytest.fixture
def site(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "events", "website"]
    org.save()
    return make_website(
        org,
        public_key=KEY,
        state="public",
        privacy_mode="link",
        privacy_url="https://example.org/datenschutz",
    )


@pytest.fixture
def zug(orgs):
    return Department.objects.create(organization=orgs["a"], parent=orgs["a"], name="Jägerzug")


@pytest.fixture
def editor(orgs):
    user = make_user("untereinheit-abschnitte@example.org")
    give_role(user, orgs["a"], permissions=["website.content"], name="Schriftführer")
    return user


def url(org, rest=""):
    return f"/api/orgs/{org.pk}/website/{rest}"


def unit_page():
    resp = Client().get(f"/api/public/site/v1/{KEY}/units/jaegerzug/")
    assert resp.status_code == 200, resp.content
    return resp.json()


def new_unit_text(c, org, zug):
    resp = c.post(
        url(org, "texts/"),
        {"kind": "unit", "department": zug.pk, "title": "Jägerzug", "body": "Seit 1955."},
        "application/json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()["id"]


def test_ohne_abschnitte_wie_bisher(orgs, editor, api, site, zug):
    # Auch ganz ohne Text hat die Seite die festen Blöcke in der bisherigen Reihenfolge
    assert [s["kind"] for s in unit_page()["sections"]] == list(UNIT_BUILTINS)
    c = api(editor)
    pk = new_unit_text(c, orgs["a"], zug)
    data = c.get(url(orgs["a"], f"texts/{pk}/")).json()
    assert [s["key"] for s in data["sections"]] == list(UNIT_BUILTINS)
    c.post(url(orgs["a"], f"texts/{pk}/publish/"))
    out = unit_page()
    assert out["text"] and [s["kind"] for s in out["sections"]] == list(UNIT_BUILTINS)
    # Auswahl in der Verwaltung: feste Blöcke der Untereinheit, kein Titelbild
    options = c.get(url(orgs["a"], "texts/")).json()["unit_section_options"]
    assert set(options["home_labels"]) == set(UNIT_BUILTINS)
    assert "cover" not in options["home_kinds"] and "text_image" in options["home_kinds"]


def test_eigene_abschnitte_und_feste_bloecke(orgs, editor, api, site, zug):
    c = api(editor)
    pk = new_unit_text(c, orgs["a"], zug)
    sections = [
        {"key": "c:z1", "kind": "quote", "on": True, "data": {"text": "Zugluft macht frei."}},
        {"key": "events", "on": True},
        {"key": "body", "on": True, "width": "text"},
        {"key": "contact", "on": False},
        {
            "key": "c:h1",
            "kind": "hours",
            "on": True,
            "data": {"title": "Training", "items": [{"day": "Dienstag", "time": "19–21 Uhr"}]},
        },
    ]
    resp = c.put(url(orgs["a"], f"texts/{pk}/"), {"sections": sections}, "application/json")
    assert resp.status_code == 200, resp.content
    saved = [s["key"] for s in resp.json()["sections"]]
    # Fehlende feste Blöcke hängen hinten an
    assert saved[:5] == ["c:z1", "events", "body", "contact", "c:h1"]
    assert set(saved) == {"c:z1", "c:h1", *UNIT_BUILTINS}
    c.post(url(orgs["a"], f"texts/{pk}/publish/"))
    kinds = [s["kind"] for s in unit_page()["sections"]]
    # Ausgeschalteter Kontakt fehlt
    assert kinds == ["quote", "events", "body", "hours", "homepage", "honors", "news", "follow"]
    # Suche findet den Text eigener Abschnitte
    hits = search.search(SiteView(site), "zugluft", lambda: [])
    assert [h["kind"] for h in hits] == ["unit"]


def test_abschnitte_werden_geprueft(orgs, editor, api, site, zug):
    c = api(editor)
    pk = new_unit_text(c, orgs["a"], zug)
    for bad in (
        [{"key": "c:c1", "kind": "cover", "on": True, "data": {}}],
        [{"key": "c:t1", "kind": "gibtsnicht", "on": True, "data": {}}],
        [{"key": "greeting", "on": True}],
    ):
        resp = c.put(url(orgs["a"], f"texts/{pk}/"), {"sections": bad}, "application/json")
        assert resp.status_code == 400, bad
    # Feste Blöcke der Untereinheit gibt es auf Textseiten nicht
    resp = c.post(
        url(orgs["a"], "texts/"),
        {
            "kind": "page",
            "slug": "verein",
            "title": "Verein",
            "sections": [{"key": "contact", "on": True}],
        },
        "application/json",
    )
    assert resp.status_code == 400


def test_bildplatz_ohne_bild_nur_in_der_vorschau(orgs, editor, api, site, zug):
    c = api(editor)
    pk = new_unit_text(c, orgs["a"], zug)
    sections = [
        {"key": "body", "on": True},
        {
            "key": "c:t1",
            "kind": "text_image",
            "on": True,
            "data": {
                "title": "Probe",
                "text": "Jeden Dienstag.",
                "image_note": "Probenszene, Querformat",
            },
        },
        {
            "key": "c:b1",
            "kind": "images",
            "on": True,
            "data": {"items": [{"image": None, "note": "Gruppenbild"}]},
        },
    ]
    resp = c.put(url(orgs["a"], f"texts/{pk}/"), {"sections": sections}, "application/json")
    assert resp.status_code == 200, resp.content
    c.post(url(orgs["a"], f"texts/{pk}/publish/"))
    out = {s["kind"]: s for s in unit_page()["sections"]}
    # Veröffentlicht: kein Platzhalter, „Bilder“ ohne Bild entfällt ganz
    assert out["text_image"]["image"] is None and "placeholder" not in out["text_image"]
    assert "images" not in out
    # Vorschau (Entwurf): Platzhalter mit Notiz
    site.draft_shown = True
    preview = {s["kind"]: s for s in SiteView(site).unit_detail(zug)["sections"]}
    assert preview["text_image"]["placeholder"] == "Probenszene, Querformat"
    assert preview["images"]["items"] == [
        {"image": None, "caption": "", "placeholder": "Gruppenbild"}
    ]


def test_fassung_bringt_abschnitte_zurueck(orgs, editor, api, site, zug):
    c = api(editor)
    pk = new_unit_text(c, orgs["a"], zug)
    sections = [{"key": "c:z1", "kind": "quote", "on": True, "data": {"text": "Horrido!"}}]
    c.put(url(orgs["a"], f"texts/{pk}/"), {"sections": sections}, "application/json")
    c.post(url(orgs["a"], f"texts/{pk}/publish/"))
    c.put(url(orgs["a"], f"texts/{pk}/"), {"sections": []}, "application/json")
    rev = WebsiteText.objects.get(pk=pk).revisions.order_by("-published_at", "-pk").first()
    data = c.post(url(orgs["a"], f"texts/{pk}/revisions/{rev.pk}/restore/")).json()
    assert "c:z1" in [s["key"] for s in data["sections"]]
