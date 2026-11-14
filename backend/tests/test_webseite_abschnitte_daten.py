"""Abschnittsarten mit Daten aus HUBIplan (Ralf 14.11.2026): Majestäten einer Untereinheit,
Ergebnisse eines Wettbewerbs, Galerie-Übersicht, Neueste Beiträge, Mitgliederbereich und App,
Zahlen aus HUBIplan. Alle Daten erfunden."""

import datetime

import pytest
from django.test import Client
from django.utils import timezone

from competitions.models import Competition
from core.tenancy import rls_bypass
from organizations.models import Department
from website.content_models import GalleryAlbum, GalleryItem
from website.models import Website, WebsiteImage

from .factories import give_role, make_member, make_user

pytestmark = pytest.mark.django_db(transaction=True)
KEY = "daten-a"


@pytest.fixture
def club(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "events", "website", "competitions", "honors"]
    org.founding_year = 1920
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
        blocks={"results": True, "gallery": True, "units": True, "posts": True},
    )


@pytest.fixture
def manager(club, api):
    user = make_user("daten@example.org")
    give_role(user, club, permissions=["website.manage"], name="Webseite")
    return api(user)


def url(club):
    return f"/api/orgs/{club.pk}/website/"


def custom(key, kind, data):
    return {"key": f"c:{key}", "kind": kind, "on": True, "data": data}


def layout():
    return Client().get(f"/api/public/site/v1/{KEY}/").json()["home_layout"]


def put(manager, club, sections):
    return manager.put(url(club), {"home_sections": sections}, "application/json")


def test_auswahl_und_zahlen(club, site, manager):
    zug = Department.objects.create(organization=club, parent=club, name="Jägerzug")
    make_member(club, "Erika", "Beispiel", departments=[zug])
    make_member(club, "Max", "Muster")
    comp = Competition.objects.create(
        organization=club,
        title="Pokalschießen",
        date=datetime.date(2026, 10, 3),
        website="abschluss",
        status="endgueltig",
    )
    Competition.objects.create(
        organization=club, title="Intern", date=datetime.date(2026, 9, 1), website="aus"
    )
    data = manager.get(url(club)).json()
    choices = data["home_choices"]
    assert [c["title"] for c in choices["competitions"]] == ["Pokalschießen"]
    assert "Jägerzug" in [u["name"] for u in choices["units"]]
    for kind in ("unit_honors", "competition", "albums", "posts", "app", "live_facts"):
        assert kind in data["home_kinds"]

    album = GalleryAlbum.objects.create(
        organization=club, website=site, title="Festzug", slug="festzug", published=True
    )
    img = WebsiteImage.objects.create(organization=club, website=site, key="fz1", alt_text="x")
    GalleryItem.objects.create(organization=club, album=album, image=img, position=0)

    sections = [
        custom("w", "competition", {"competition": comp.pk}),
        custom("a", "albums", {"count": 2}),
        custom("p", "posts", {"count": 3}),
        custom("x", "app", {"text": "Alles dabei", "qr": True, "store": False}),
        custom(
            "z",
            "live_facts",
            {"items": [{"fact": "members"}, {"fact": "years", "label": "Jahre jung"}]},
        ),
        custom("m", "unit_honors", {"unit": zug.pk}),
    ]
    resp = put(manager, club, sections)
    assert resp.status_code == 200, resp.content
    out = {s["kind"]: s for s in layout() if s["key"].startswith("c:")}
    assert out["competition"]["competition"]["title"] == "Pokalschießen"
    assert len(out["competition"]["competition"]["id"]) == 20
    assert [a["title"] for a in out["albums"]["albums"]] == ["Festzug"]
    assert "posts" not in out  # keine Beiträge
    assert out["app"]["login_url"].endswith("/anmelden") and out["app"]["store_url"] == ""
    years = timezone.localdate().year - 1920
    assert out["live_facts"]["items"] == [
        {"value": "2", "label": "Mitglieder"},
        {"value": str(years), "label": "Jahre jung"},
    ]
    assert "unit_honors" not in out  # keine Majestäten im Zug


@pytest.mark.parametrize(
    "kind,data",
    [
        ("live_facts", {"items": [{"fact": "geheim"}]}),
        ("live_facts", {"items": [{"fact": "members"}, {"fact": "members"}]}),
    ],
)
def test_pruefung(club, site, manager, kind, data):
    assert put(manager, club, [custom("x", kind, data)]).status_code == 400


def test_fremde_verweise_fallen_weg(club, site, manager, orgs):
    with rls_bypass():
        fremd = Competition.objects.create(
            organization=orgs["b"],
            title="Fremd",
            date=datetime.date(2026, 10, 3),
            website="abschluss",
            status="endgueltig",
        )
    resp = put(manager, club, [custom("w", "competition", {"competition": fremd.pk})])
    assert resp.status_code == 200
    saved = [s for s in resp.json()["website"]["home_sections"] if s["key"] == "c:w"][0]
    assert saved["data"]["competition"] is None
