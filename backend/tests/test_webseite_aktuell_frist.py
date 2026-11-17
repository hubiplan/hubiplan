"""Wie lange etwas auf der Startseite als aktuell gilt (Ralf 14.11.2026): Frist in Tagen für
„Aktuelle Ergebnisse“, „Ergebnisse eines Wettbewerbs“, „Galerie-Übersicht“ und „Neueste
Beiträge“. Ist nichts mehr aktuell, verschwindet der Abschnitt. Alle Daten erfunden."""

import datetime

import pytest
from django.test import Client
from django.utils import timezone

from competitions.models import Competition
from website.content_models import GalleryAlbum, GalleryItem
from website.home import normalize
from website.models import DEFAULT_HOME_OFF, HOME_SECTIONS, WebsiteImage
from website.social_models import SocialFeed, SocialPost

from .factories import give_role, make_user, make_website

pytestmark = pytest.mark.django_db(transaction=True)
KEY = "frist-a"


@pytest.fixture
def club(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "events", "website", "competitions", "social"]
    org.save()
    return org


@pytest.fixture
def site(club):
    return make_website(
        club,
        public_key=KEY,
        state="public",
        privacy_mode="link",
        privacy_url="https://example.org/datenschutz",
        blocks={"results": True, "gallery": True, "posts": True},
    )


@pytest.fixture
def manager(club, api):
    user = make_user("frist@example.org")
    give_role(user, club, permissions=["website.manage"], name="Webseite")
    return api(user)


def put(manager, club, sections):
    return manager.put(
        f"/api/orgs/{club.pk}/website/", {"home_sections": sections}, "application/json"
    )


def public(path=""):
    return Client().get(f"/api/public/site/v1/{KEY}/{path}")


def days_ago(n):
    return timezone.localdate() - datetime.timedelta(days=n)


def comp(club, title, age, status="endgueltig", website="abschluss"):
    return Competition.objects.create(
        organization=club, title=title, date=days_ago(age), website=website, status=status
    )


def custom(key, kind, data):
    return {"key": f"c:{key}", "kind": kind, "on": True, "data": data}


def test_frist_wird_geprueft_und_gespeichert():
    out = normalize(
        [{"key": "results", "on": True, "days": 30}, {"key": "events", "on": True, "days": 30}],
        HOME_SECTIONS,
        DEFAULT_HOME_OFF,
    )
    by_key = {s["key"]: s for s in out}
    assert by_key["results"]["days"] == 30
    assert "days" not in by_key["events"]  # nur bei Bausteinen mit Frist
    for bad in (0, 31, -3, "30", True, 1000):
        out = normalize([{"key": "results", "on": True, "days": bad}], HOME_SECTIONS, set())
        assert out[0]["days"] is None  # Unbekanntes heißt „immer“


def test_aktuelle_ergebnisse_nur_bis_frist(club, site, manager):
    comp(club, "Frühjahrsschießen", 100)
    comp(club, "Pokalschießen", 10)
    comp(club, "Vereinsmeisterschaft", 200, status="vorlaeufig", website="live")

    def titles(days):
        entry = {"key": "results", "on": True, "days": days}
        resp = put(manager, club, [entry])
        assert resp.status_code == 200, resp.content
        results = next(s for s in resp.json()["website"]["home_sections"] if s["key"] == "results")
        assert results["days"] == days
        return [c["title"] for c in public("results/?start=1").json()["competitions"]]

    # ohne Frist wie bisher: die drei neuesten
    assert titles(None) == ["Pokalschießen", "Frühjahrsschießen", "Vereinsmeisterschaft"]
    # 30 Tage: das alte endgültige fällt weg, das vorläufige bleibt
    assert titles(30) == ["Pokalschießen", "Vereinsmeisterschaft"]
    # 7 Tage und nichts Laufendes: nichts mehr aktuell, der Baustein bleibt leer
    Competition.objects.filter(title="Vereinsmeisterschaft").update(status="endgueltig")
    assert titles(7) == []
    # Die Übersicht der Ergebnisse zeigt weiter alles
    overview = public("results/").json()["competitions"]
    assert len(overview) == 3


def test_frist_bei_eigenen_abschnitten(club, site, manager):
    alt = comp(club, "Herbstpokal", 40)
    neu = comp(club, "Martinsschießen", 2)
    fest = GalleryAlbum.objects.create(
        organization=club,
        website=site,
        title="Schützenfest",
        slug="fest",
        published=True,
        date=days_ago(60),
    )
    zug = GalleryAlbum.objects.create(
        organization=club,
        website=site,
        title="Martinszug",
        slug="zug",
        published=True,
        date=days_ago(3),
    )
    ohne = GalleryAlbum.objects.create(
        organization=club, website=site, title="Allerlei", slug="allerlei", published=True
    )
    for i, album in enumerate((fest, zug, ohne)):
        img = WebsiteImage.objects.create(
            organization=club, website=site, key=f"bild{i}", alt_text="Bild"
        )
        GalleryItem.objects.create(organization=club, album=album, image=img, position=0)
    feed = SocialFeed.objects.create(
        organization=club,
        website=site,
        kind="instagram",
        status="ok",
        account_name="musterverein",
    )
    for n, age in (("alt", 50), ("neu", 1)):
        SocialPost.objects.create(
            organization=club,
            feed=feed,
            external_id=n,
            media_type="text",
            text=f"Beitrag {n}",
            published_at=timezone.now() - datetime.timedelta(days=age),
            state="visible",
        )

    sections = [
        custom("w1", "competition", {"competition": alt.pk, "days": 30}),
        custom("w2", "competition", {"competition": neu.pk, "days": 30}),
        custom("a", "albums", {"count": 4, "days": 30}),
        custom("p", "posts", {"count": 3, "days": 30}),
    ]
    resp = put(manager, club, sections)
    assert resp.status_code == 200, resp.content
    saved = {s["key"]: s for s in resp.json()["website"]["home_sections"] if "kind" in s}
    assert saved["c:a"]["data"]["days"] == 30

    out = {s["key"]: s for s in public().json()["home_layout"] if s["key"].startswith("c:")}
    assert "c:w1" not in out  # Herbstpokal ist älter als 30 Tage
    assert out["c:w2"]["competition"]["title"] == "Martinsschießen"
    assert [a["title"] for a in out["c:a"]["albums"]] == ["Martinszug"]  # ohne Datum fällt weg
    assert [p["text"] for p in out["c:p"]["posts"]] == ["Beitrag neu"]

    # Ohne Frist wie bisher
    for s in sections:
        s["data"].pop("days")
    assert put(manager, club, sections).status_code == 200
    out = {s["key"]: s for s in public().json()["home_layout"] if s["key"].startswith("c:")}
    assert "c:w1" in out
    assert len(out["c:a"]["albums"]) == 3
    assert len(out["c:p"]["posts"]) == 2

    # Laufender Wettbewerb bleibt trotz Frist stehen
    Competition.objects.filter(pk=alt.pk).update(status="laeuft", website="live")
    sections[0]["data"]["days"] = 7
    assert put(manager, club, sections).status_code == 200
    out = {s["key"]: s for s in public().json()["home_layout"] if s["key"].startswith("c:")}
    assert "c:w1" in out
