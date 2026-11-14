"""Suche auf der Webseite findet alles öffentlich Sichtbare (Ralf 14.11.2026: „Fahnenschwenker“
stand in einer Kachel der Startseite und wurde nicht gefunden). Alles erfunden."""

import datetime

import pytest
from django.test import Client

from organizations.models import Department
from website.models import Website, WebsiteText

pytestmark = pytest.mark.django_db(transaction=True)
KEY = "suche-a"
WHEN = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)

TILES = {
    "key": "c:k1",
    "kind": "tiles",
    "on": True,
    "data": {
        "title": "Wo du mitmachen kannst",
        "tiles": [
            {"title": "Bei den Fahnenschwenkern", "text": "Du schwenkst die Fahnen des Vereins."},
            {"title": "Im Spielmannszug", "text": "Trommeln und Flöten."},
        ],
    },
}
FAQ_OFF = {
    "key": "c:f1",
    "kind": "faq",
    "on": False,
    "data": {"title": "Fragen", "items": [{"question": "Ausgeschaltet?", "answer": "Geheimwort"}]},
}


@pytest.fixture
def club(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "events", "website"]
    org.save()
    return org


@pytest.fixture
def site(club):
    site = Website.objects.create(organization=club, public_key=KEY, state="public")
    site.blocks = {**(site.blocks or {}), "search": True, "units": True}
    site.home_sections = [{"key": "greeting", "on": True}, TILES, FAQ_OFF]
    site.save()
    return site


def hits(q):
    resp = Client().get(f"/api/public/site/v1/{KEY}/search/", {"q": q})
    assert resp.status_code == 200
    return resp.json()["results"]


def test_kachel_der_startseite_mit_wortteil(site):
    [hit] = hits("fahnenschwenker")
    assert hit["kind"] == "home"
    assert hit["key"] == "c:k1"
    assert hit["title"] == "Wo du mitmachen kannst"
    assert "Fahnenschwenkern" in hit["text"]
    assert hits("SPIELMANN flöten")[0]["key"] == "c:k1"
    # Akzente egal
    assert hits("floten")[0]["key"] == "c:k1"


def test_begruessung(club, site):
    WebsiteText.objects.create(
        organization=club,
        website=site,
        kind=WebsiteText.Kind.GREETING,
        title="Entwurf",
        body="Noch nicht veröffentlicht: Maibaum",
        published_title="Willkommen",
        published_body="Schön, dass du da bist. Wir feiern **Schützenfest**.",
        published_at=WHEN,
    )
    [hit] = hits("schützenfest")
    assert hit == {
        "kind": "home",
        "key": "greeting",
        "title": "Willkommen",
        "text": "Schön, dass du da bist. Wir feiern Schützenfest.",
    }
    assert hits("maibaum") == []
    site.home_sections = [{"key": "greeting", "on": False}, TILES]
    site.save()
    assert hits("schützenfest") == []


def test_entwuerfe_und_ausgeschaltetes_nicht(club, site):
    assert hits("geheimwort") == []
    site.draft = {"home_sections": [{**TILES, "data": {**TILES["data"], "title": "Kegelbahn"}}]}
    site.save()
    assert hits("kegelbahn") == []
    WebsiteText.objects.create(
        organization=club,
        website=site,
        kind=WebsiteText.Kind.PAGE,
        slug="entwurf",
        title="Kegelbahn",
        body="Kegelbahn",
    )
    assert hits("kegelbahn") == []


def test_abschnitte_einer_textseite(club, site):
    WebsiteText.objects.create(
        organization=club,
        website=site,
        kind=WebsiteText.Kind.PAGE,
        slug="mitmachen",
        title="Mitmachen",
        published_title="Mitmachen",
        published_body="Komm vorbei.",
        published_sections=[
            {"key": "body", "on": True},
            {
                "key": "c:f2",
                "kind": "faq",
                "on": True,
                "data": {
                    "title": "Fragen",
                    "items": [
                        {"question": "Was kostet die Uniform?", "answer": "Der Verein leiht sie."}
                    ],
                },
            },
        ],
        published_at=WHEN,
    )
    [hit] = hits("uniform")
    assert hit["kind"] == "page"
    assert hit["slug"] == "mitmachen"
    assert "Uniform" in hit["text"]


def test_untereinheit(club, site):
    zug = Department.objects.create(organization=club, parent=club, name="Jägerzug Hubertus")
    WebsiteText.objects.create(
        organization=club,
        website=site,
        kind=WebsiteText.Kind.UNIT,
        department=zug,
        published_title="Jägerzug",
        published_body="Wir marschieren seit 1955 mit Hörnern.",
        published_at=WHEN,
    )
    [hit] = hits("hörnern")
    assert hit == {
        "kind": "unit",
        "slug": "jaegerzug-hubertus",
        "title": "Jägerzug",
        "text": "Wir marschieren seit 1955 mit Hörnern.",
    }
    assert hits("jägerzug hubertus")[0]["kind"] == "unit"
    site.units_mode = Website.Units.NONE
    site.save()
    assert hits("hörnern") == []
