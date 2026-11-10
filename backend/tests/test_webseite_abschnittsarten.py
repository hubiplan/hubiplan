"""Weitere Abschnittsarten der Startseite und Textseiten (Ralf 10.11.2026 „alle 9“):
Häufige Fragen, Partner, Anfahrt, Termine einer Art, Dokument, Video als Link, Auszug aus der
Chronik, Zahlen, Trenner. Alle Daten erfunden."""

import datetime

import pytest
from django.test import Client
from django.utils import timezone

from core.tenancy import rls_bypass
from events.models import Event, EventCategory
from places.models import Place
from website.content_models import WebsiteDocument, WebsiteText
from website.models import Website, WebsiteImage

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db(transaction=True)
KEY = "abschnittsarten-a"


@pytest.fixture
def club(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "events", "website", "chronicle"]
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
        blocks={"events": True, "contact": True, "history": True, "statutes": True},
    )


@pytest.fixture
def manager(club, api):
    user = make_user("abschnittsarten@example.org")
    give_role(user, club, permissions=["website.manage"], name="Webseite")
    return api(user)


def url(club, path=""):
    return f"/api/orgs/{club.pk}/website/{path}"


def custom(key, kind, data):
    return {"key": f"c:{key}", "kind": kind, "on": True, "data": data}


def layout():
    return Client().get(f"/api/public/site/v1/{KEY}/").json()["home_layout"]


@pytest.fixture
def stuff(club, site):
    logo = WebsiteImage.objects.create(
        organization=club, website=site, key="partnerlogo", alt_text="Logo"
    )
    place = Place.objects.create(
        organization=club,
        name="Schützenhalle",
        address="Musterweg 1, 12345 Musterstadt",
        directions="Parken hinter der Halle.",
    )
    schiessen = EventCategory.objects.create(organization=club, name="Schießen")
    fest = EventCategory.objects.create(organization=club, name="Fest")
    start = timezone.now() + datetime.timedelta(days=3)
    with rls_bypass():
        for i in range(3):
            Event.objects.create(
                organization=club,
                title=f"Training {i + 1}",
                visibility="public",
                category=schiessen,
                starts_at=start + datetime.timedelta(days=7 * i),
                ends_at=start + datetime.timedelta(days=7 * i, hours=2),
            )
        Event.objects.create(
            organization=club,
            title="Schützenfest",
            visibility="public",
            category=fest,
            starts_at=start,
            ends_at=start + datetime.timedelta(hours=5),
        )
    doc = WebsiteDocument.objects.create(
        organization=club,
        website=site,
        section="documents",
        key=WebsiteDocument.new_key(),
        title="Aufnahmeantrag",
        file="webseite/aufnahme.pdf",
        content_type="application/pdf",
        size=120_000,
    )
    WebsiteText.objects.create(
        organization=club,
        website=site,
        kind="page",
        slug="geschichte",
        title="Chronik",
        published_title="Chronik",
        published_at=timezone.now(),
        published_timeline=[
            {"year": 1920, "title": "Gründung"},
            {"year": 1950, "kind": "chapter", "title": "Neubeginn"},
            {"year": 1975, "title": "Neue Fahne"},
            {"year": 2020, "title": "100 Jahre", "text": "Großes Fest."},
        ],
    )
    return {"logo": logo, "place": place, "category": schiessen, "doc": doc}


def test_alle_neuen_arten(club, site, manager, stuff):
    choices = manager.get(url(club)).json()["home_choices"]
    assert [p["name"] for p in choices["places"]] == ["Schützenhalle"]
    assert {c["name"] for c in choices["categories"]} == {"Schießen", "Fest"}
    assert [d["title"] for d in choices["documents"]] == ["Aufnahmeantrag"]
    sections = [
        {"key": "greeting", "on": False},
        custom(
            "f",
            "faq",
            {
                "title": "Fragen",
                "items": [
                    {"question": "Wie werde ich Mitglied?", "answer": "Schreib uns."},
                    {"question": "", "answer": "fällt weg"},
                ],
            },
        ),
        custom(
            "p",
            "partners",
            {
                "items": [
                    {
                        "name": "Bäckerei Muster",
                        "image": stuff["logo"].pk,
                        "url": "https://example.org/baeckerei",
                    },
                    {"name": "Ohne Logo", "image": None, "url": ""},
                ]
            },
        ),
        custom("a", "directions", {"place": stuff["place"].pk, "text": "Eingang links."}),
        custom("t", "event_list", {"category": stuff["category"].pk, "count": 2}),
        custom("d", "document", {"document": stuff["doc"].pk, "label": ""}),
        custom(
            "v",
            "video",
            {"title": "Festzug", "url": "https://example.org/video", "image": stuff["logo"].pk},
        ),
        custom("c", "chronicle", {"count": 2}),
        custom(
            "z",
            "facts",
            {"items": [{"value": "1920", "label": "gegründet"}, {"value": "6", "label": "Züge"}]},
        ),
        custom("x", "divider", {"style": "space", "size": "large"}),
    ]
    resp = manager.put(url(club), {"home_sections": sections}, "application/json")
    assert resp.status_code == 200, resp.content
    out = {s["kind"]: s for s in layout() if s["key"].startswith("c:")}
    assert list(out) == [
        "faq",
        "partners",
        "directions",
        "event_list",
        "document",
        "video",
        "chronicle",
        "facts",
        "divider",
    ]
    assert [i["question"] for i in out["faq"]["items"]] == ["Wie werde ich Mitglied?"]
    assert out["partners"]["items"][0]["image"]["url"]
    assert out["partners"]["items"][1]["image"] is None
    assert out["directions"]["name"] == "Schützenhalle"
    assert out["directions"]["route_url"].startswith("https://www.openstreetmap.org/")
    assert out["directions"]["title"] == "Schützenhalle"
    assert [e["title"] for e in out["event_list"]["events"]] == ["Training 1", "Training 2"]
    assert out["document"]["label"] == "Aufnahmeantrag" and out["document"]["file_type"] == "pdf"
    assert out["video"]["url"] == "https://example.org/video" and out["video"]["image"]
    # Neueste Einträge zuerst, Kapitel zählen nicht
    assert [e["title"] for e in out["chronicle"]["entries"]] == ["100 Jahre", "Neue Fahne"]
    assert [f["value"] for f in out["facts"]["items"]] == ["1920", "6"]
    assert out["divider"] == {**out["divider"], "style": "space", "size": "large"}


def test_pruefung_und_bereiche(club, site, manager, stuff):
    # Fremde Adressen nur mit https://, Listen begrenzt
    bad = custom("v", "video", {"url": "javascript:alert(1)"})
    assert manager.put(url(club), {"home_sections": [bad]}, "application/json").status_code == 400
    many = custom("f", "faq", {"items": [{"question": f"F{i}"} for i in range(13)]})
    assert manager.put(url(club), {"home_sections": [many]}, "application/json").status_code == 400
    # Unbekannte Verweise fallen weg, der Abschnitt erscheint dann nicht
    resp = manager.put(
        url(club),
        {"home_sections": [custom("a", "directions", {"place": 999999})]},
        "application/json",
    )
    assert resp.status_code == 200
    assert not [s for s in layout() if s["key"] == "c:a"]
    # Termine und Chronik nur mit eingeschaltetem Bereich
    manager.put(
        url(club),
        {
            "home_sections": [
                custom("t", "event_list", {"category": stuff["category"].pk}),
                custom("c", "chronicle", {}),
            ],
            "blocks": {"events": False, "history": False},
        },
        "application/json",
    )
    assert not [s for s in layout() if s["key"].startswith("c:")]


def test_auch_auf_textseiten(club, site, manager, stuff):
    resp = manager.post(
        url(club, "texts/"),
        {"kind": "page", "slug": "verein", "title": "Verein", "body": "Seit 1920."},
        "application/json",
    )
    pk = resp.json()["id"]
    sections = [
        {"key": "body", "on": True},
        custom("f", "faq", {"items": [{"question": "Wann ist Training?", "answer": "Freitags."}]}),
    ]
    assert (
        manager.put(url(club, f"texts/{pk}/"), {"sections": sections}, "application/json")
    ).status_code == 200
    manager.post(url(club, f"texts/{pk}/publish/"))
    out = Client().get(f"/api/public/site/v1/{KEY}/pages/verein/").json()["sections"]
    assert [s["kind"] for s in out] == ["body", "faq"]
