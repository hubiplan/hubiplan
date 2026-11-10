"""Abschnitte der Startseite (Konzept webseite-baukasten G3, Ralf 10.11.2026).
Alle Daten erfunden."""

import datetime

import pytest
from django.test import Client
from django.utils import timezone

from access.models import Role, RoleAssignment
from core.tenancy import rls_bypass
from events.models import Event
from website import services
from website.content_models import GalleryAlbum, GalleryItem
from website.models import Website, WebsiteImage

from .factories import give_role, make_member, make_user

pytestmark = pytest.mark.django_db(transaction=True)
KEY = "abschnitte-a"


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
def client_web(club, api):
    user = make_user("web-abschnitte@example.org")
    give_role(user, club, permissions=["website.manage"], name="Webseite")
    return api(user)


def url(club, path=""):
    return f"/api/orgs/{club.pk}/website/{path}"


def put_home(c, club, sections):
    return c.put(url(club), {"home_sections": sections}, "application/json")


def public(preview_site=None):
    headers = {}
    if preview_site is not None:
        session, _ = services.exchange(preview_site, services.open_token(preview_site))
        headers["HTTP_X_PREVIEW_SESSION"] = session
    return Client().get(f"/api/public/site/v1/{KEY}/", **headers).json()


def custom(key, kind, data, **extra):
    return {"key": f"c:{key}", "kind": kind, "on": True, "data": data, **extra}


def test_eigene_abschnitte_speichern_und_zeigen(club, site, client_web):
    image = WebsiteImage.objects.create(
        organization=club, website=site, key="bannerbild", alt_text="Festzug"
    )
    resp = put_home(
        client_web,
        club,
        [
            {"key": "greeting", "on": True, "bg": "light", "width": "text"},
            custom("text1", "text", {"title": "Willkommen", "text": "Schön, dass Sie da sind."}),
            custom(
                "ban1",
                "banner",
                {"image": image.pk, "line": "Schützenfest", "height": "high"},
                bg="p1",
                width="full",
            ),
            custom(
                "knopf1",
                "buttons",
                {
                    "buttons": [
                        {"label": "Mitglied werden", "target": {"page": "contact"}},
                        {"label": "Programm", "target": {"url": "https://example.org/programm"}},
                        {"label": "Ohne Ziel", "target": None},
                    ],
                    "align": "center",
                },
            ),
            custom("leer1", "text", {"title": "", "text": ""}),
            custom(
                "zitat1",
                "quote",
                {"text": "Einigkeit macht stark.", "name": "Erika Beispiel"},
                column="main",
            ),
        ],
    )
    assert resp.status_code == 200, resp.content
    sections = resp.json()["website"]["home_sections"]
    banner = next(s for s in sections if s["key"] == "c:ban1")
    assert banner["data"]["image"] == image.pk and banner["bg"] == "p1"
    # Bausteine bleiben vollständig; eigene Abschnitte stehen dazwischen
    assert {s["key"] for s in sections} >= {"carousel", "events", "units", "c:text1"}

    # Veröffentlicht ist noch nichts verändert worden: ohne Entwurf direkt live
    data = public()
    layout = {s["key"]: s for s in data["home_layout"]}
    assert "c:leer1" not in layout  # ohne Inhalt fällt der Abschnitt weg
    assert layout["greeting"]["kind"] == "greeting" and layout["greeting"]["width"] == "text"
    assert layout["c:text1"]["title"] == "Willkommen"
    assert layout["c:ban1"]["image"]["url"].endswith("/")
    assert layout["c:ban1"]["height"] == "high" and layout["c:ban1"]["width"] == "full"
    buttons = layout["c:knopf1"]["buttons"]
    assert [b["label"] for b in buttons] == ["Mitglied werden", "Programm"]
    assert buttons[0]["target"]["key"] == "contact"
    assert buttons[1]["target"] == {"key": "link", "url": "https://example.org/programm"}
    assert layout["c:zitat1"]["column"] == "main"
    assert layout["events"]["column"] == "side"
    # Ältere Webseiten lesen weiter „home“ nur mit den festen Bausteinen
    assert all(not k.startswith("c:") for k in data["home"])
    # Das Bild des Banners darf öffentlich ausgeliefert werden, ein anderes nicht
    from website.public import SiteView

    site.refresh_from_db()
    assert SiteView(site).public_image("bannerbild") is not None
    WebsiteImage.objects.create(organization=club, website=site, key="privat", alt_text="x")
    assert SiteView(site).public_image("privat") is None


@pytest.mark.parametrize(
    "section",
    [
        {"key": "c:x1", "kind": "unbekannt", "on": True, "data": {}},
        {"key": "frei", "kind": "text", "on": True, "data": {}},
        custom("x2", "text", {"title": "A" * 151}),
        custom("x3", "buttons", {"buttons": [{"label": "a"}] * 4}),
        custom("x4", "tiles", {"tiles": [{"title": "a"}] * 7}),
        custom("x5", "contacts", {"roles": [1, 2, 3, 4, 5]}),
        custom("x6", "buttons", {"buttons": [{"label": "a", "target": {"url": "javascript:x"}}]}),
        custom("x7", "text", ["kein", "dict"]),
    ],
)
def test_abschnitte_werden_geprueft(club, site, client_web, section):
    assert put_home(client_web, club, [section]).status_code == 400


def test_unbekannte_verweise_fallen_weg(club, site, client_web, orgs):
    other = WebsiteImage.objects.create(
        organization=club, website=site, key="anderes", alt_text="x"
    )
    resp = put_home(
        client_web,
        club,
        [
            custom("ti1", "text_image", {"title": "T", "image": other.pk + 999, "side": "links"}),
            custom("ap1", "contacts", {"roles": [987654]}),
            custom(
                "kn1", "buttons", {"buttons": [{"label": "X", "target": {"page": "gibtsnicht"}}]}
            ),
        ],
    )
    assert resp.status_code == 200, resp.content
    by_key = {s["key"]: s for s in resp.json()["website"]["home_sections"]}
    assert by_key["c:ti1"]["data"]["image"] is None
    assert by_key["c:ti1"]["data"]["side"] == "right"
    assert by_key["c:ap1"]["data"]["roles"] == []
    assert by_key["c:kn1"]["data"]["buttons"][0]["target"] is None


def test_termin_ansprechpartner_und_album(club, site, client_web):
    erika = make_member(club, "Erika", "Beispiel", email="erika@example.org")
    chair = Role.objects.create(organization=club, name="1. Vorsitzende", on_website=True)
    RoleAssignment.objects.create(organization=club, role=chair, person=erika.person)
    hidden = Role.objects.create(organization=club, name="Intern", on_website=False)
    start = timezone.now() + datetime.timedelta(days=10)
    with rls_bypass():
        fest = Event.objects.create(
            organization=club,
            title="Schützenfest",
            visibility="public",
            starts_at=start,
            ends_at=start + datetime.timedelta(hours=5),
        )
        intern = Event.objects.create(
            organization=club,
            title="Vorstandssitzung",
            visibility="members",
            starts_at=start,
            ends_at=start + datetime.timedelta(hours=1),
        )
    album = GalleryAlbum.objects.create(
        organization=club, website=site, title="Festzug 2026", slug="festzug-2026", published=True
    )
    for i in range(6):
        img = WebsiteImage.objects.create(
            organization=club, website=site, key=f"festzug{i}", alt_text=f"Bild {i}"
        )
        GalleryItem.objects.create(organization=club, album=album, image=img, position=i)
    site.blocks = {"gallery": True, "events": True, "contact": True}
    site.save()

    choices = client_web.get(url(club)).json()["home_choices"]
    assert [r["name"] for r in choices["roles"]] == ["1. Vorsitzende"]
    assert [e["title"] for e in choices["events"]] == ["Schützenfest"]
    assert [a["title"] for a in choices["albums"]] == ["Festzug 2026"]

    resp = put_home(
        client_web,
        club,
        [
            custom("t1", "event", {"event": fest.pk}),
            custom("t2", "event", {"event": intern.pk}),
            custom("a1", "contacts", {"roles": [hidden.pk, chair.pk]}),
            custom("g1", "album", {"album": album.pk, "count": 4}),
        ],
    )
    assert resp.status_code == 200, resp.content
    by_key = {s["key"]: s for s in resp.json()["website"]["home_sections"]}
    assert by_key["c:t2"]["data"]["event"] is None  # nur öffentliche Termine
    assert by_key["c:a1"]["data"]["roles"] == [chair.pk]  # nur Rollen auf der Webseite

    layout = {s["key"]: s for s in public()["home_layout"]}
    assert layout["c:t1"]["event"]["title"] == "Schützenfest"
    assert "c:t2" not in layout
    card = layout["c:a1"]["roles"][0]
    assert card["name"] == "1. Vorsitzende" and card["holders"][0]["name"] == "Erika Beispiel"
    assert card["contact_form"] is True
    assert len(layout["c:g1"]["images"]) == 4
    assert layout["c:g1"]["album"]["slug"] == "festzug-2026"

    # Nach dem Termin verschwindet der Abschnitt
    with rls_bypass():
        Event.objects.filter(pk=fest.pk).update(
            starts_at=timezone.now() - datetime.timedelta(days=3),
            ends_at=timezone.now() - datetime.timedelta(days=2),
        )
    assert "c:t1" not in {s["key"] for s in public()["home_layout"]}


def test_abschnitte_im_entwurf(club, site, client_web):
    resp = client_web.put(
        url(club),
        {"draft": {"home_sections": [custom("neu1", "text", {"title": "Nur Entwurf"})]}},
        "application/json",
    )
    assert resp.status_code == 200, resp.content
    assert "c:neu1" not in {s["key"] for s in public()["home_layout"]}
    assert "c:neu1" in {s["key"] for s in public(site)["home_layout"]}
    assert client_web.post(url(club, "design/publish/")).status_code == 200
    assert "c:neu1" in {s["key"] for s in public()["home_layout"]}


def test_abschnitt_aus_bleibt_weg(club, site, client_web):
    put_home(client_web, club, [{**custom("z1", "quote", {"text": "Horrido"}), "on": False}])
    assert "c:z1" not in {s["key"] for s in public()["home_layout"]}
    site.refresh_from_db()
    assert all(not k.startswith("c:") for k in site.home())
