"""Hinweisleiste und Titelbild je Textseite (Konzept webseite-baukasten G6, Ralf 10.11.2026).
Alle Daten erfunden."""

import datetime

import pytest
from django.test import Client
from django.utils import timezone

from website import content
from website.models import Website, WebsiteImage

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db(transaction=True)
KEY = "g6-a"


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
    user = make_user("g6-verwaltung@example.org")
    give_role(user, club, permissions=["website.manage"], name="Webseite")
    return api(user)


@pytest.fixture
def editor(club, api):
    user = make_user("g6-inhalt@example.org")
    give_role(user, club, permissions=["website.content"], name="Schriftführer")
    return api(user)


def url(club, rest=""):
    return f"/api/orgs/{club.pk}/website/{rest}"


def info():
    return Client().get(f"/api/public/site/v1/{KEY}/").json()


def test_hinweisleiste_nur_im_zeitraum(club, site, manager):
    today = timezone.localdate()
    resp = manager.put(
        url(club),
        {
            "notice_text": "  Schützenfest   22.–25.8.: Programm ",
            "notice_target": {"page": "events"},
            "notice_from": str(today - datetime.timedelta(days=1)),
            "notice_until": str(today),
        },
        "application/json",
    )
    assert resp.status_code == 200, resp.content
    website = resp.json()["website"]
    assert website["notice_text"] == "Schützenfest 22.–25.8.: Programm"
    assert website["notice_target"] == {"page": "events"}
    notice = info()["notice"]
    assert notice["text"] == "Schützenfest 22.–25.8.: Programm"
    assert notice["target"]["key"] == "events"
    # Nach Ablauf verschwindet sie von selbst
    site.refresh_from_db()
    site.notice_until = today - datetime.timedelta(days=1)
    site.notice_from = None
    site.save()
    assert info()["notice"] is None
    # Noch nicht begonnen
    site.notice_from = today + datetime.timedelta(days=2)
    site.notice_until = None
    site.save()
    assert info()["notice"] is None
    # Ohne Zeitraum: dauerhaft, ohne Text: nie
    site.notice_from = None
    site.save()
    assert info()["notice"]["text"]
    site.notice_text = ""
    site.save()
    assert info()["notice"] is None


def test_hinweisleiste_pruefung(club, site, manager, editor):
    today = timezone.localdate()
    resp = manager.put(
        url(club),
        {"notice_from": str(today), "notice_until": str(today - datetime.timedelta(days=3))},
        "application/json",
    )
    assert resp.status_code == 400 and "notice_until" in resp.json()
    resp = manager.put(url(club), {"notice_target": {"page": "gibtsnicht"}}, "application/json")
    assert resp.status_code == 400 and "notice_target" in resp.json()
    resp = manager.put(
        url(club), {"notice_target": {"url": "javascript:alert(1)"}}, "application/json"
    )
    assert resp.status_code == 400
    resp = manager.put(
        url(club),
        {"notice_text": "Neu", "notice_target": {"url": "https://example.org/fest"}},
        "application/json",
    )
    assert resp.status_code == 200
    assert info()["notice"]["target"] == {"key": "link", "url": "https://example.org/fest"}
    # Leeres Ziel entfernt es
    resp = manager.put(url(club), {"notice_target": None}, "application/json")
    assert resp.status_code == 200 and resp.json()["website"]["notice_target"] == {}
    # Einstellungen ändert nur, wer die Webseite verwaltet
    assert editor.put(url(club), {"notice_text": "X"}, "application/json").status_code == 403


def new_page(c, club):
    resp = c.post(
        url(club, "texts/"),
        {"kind": "page", "slug": "verein", "title": "Verein", "body": "Seit 1920."},
        "application/json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()["id"]


def cover(key="c:tb", image=None):
    return {"key": key, "kind": "cover", "on": True, "data": {"image": image}}


def test_titelbild_je_textseite(club, site, editor):
    image = WebsiteImage.objects.create(
        organization=club, website=site, key="titelbild", alt_text="Festwiese"
    )
    pk = new_page(editor, club)
    options = editor.get(url(club, "texts/")).json()["section_options"]
    assert "cover" in options["home_kinds"] and "cover" in options["home_kind_hints"]
    sections = [{"key": "body", "on": True}, cover(image=image.pk)]
    resp = editor.put(url(club, f"texts/{pk}/"), {"sections": sections}, "application/json")
    assert resp.status_code == 200, resp.content
    editor.post(url(club, f"texts/{pk}/publish/"))
    out = Client().get(f"/api/public/site/v1/{KEY}/pages/verein/").json()["sections"]
    assert [s["kind"] for s in out] == ["body", "cover"]
    assert out[1]["image"]["url"]
    assert image.pk in content.used_image_ids(site)
    # Höchstens ein Titelbild je Seite
    two = [*sections, cover("c:tc", image.pk)]
    resp = editor.put(url(club, f"texts/{pk}/"), {"sections": two}, "application/json")
    assert resp.status_code == 400
    # Ohne Bild erscheint es nicht
    resp = editor.put(
        url(club, f"texts/{pk}/"),
        {"sections": [{"key": "body", "on": True}, cover()]},
        "application/json",
    )
    assert resp.status_code == 200
    editor.post(url(club, f"texts/{pk}/publish/"))
    out = Client().get(f"/api/public/site/v1/{KEY}/pages/verein/").json()["sections"]
    assert [s["kind"] for s in out] == ["body"]


def test_titelbild_nicht_auf_der_startseite(club, site, manager):
    resp = manager.put(
        url(club),
        {"home_sections": [{"key": "greeting", "on": True}, cover()]},
        "application/json",
    )
    assert resp.status_code == 400
    assert "cover" not in manager.get(url(club)).json()["home_kinds"]
