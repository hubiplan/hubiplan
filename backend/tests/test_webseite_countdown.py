"""Abschnittsart „Countdown“ (Ralf 14.11.2026): laufender Zähler bis zu einem öffentlichen
Termin oder einem frei gewählten Zeitpunkt; nach Ablauf ausblenden oder Text zeigen.
Alle Daten erfunden."""

import datetime

import pytest
from django.test import Client
from django.utils import timezone

from core.tenancy import rls_bypass
from events.models import Event
from website import home
from website.models import Website

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db(transaction=True)
KEY = "countdown-a"


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
        blocks={"events": True},
    )


@pytest.fixture
def manager(club, api):
    user = make_user("countdown@example.org")
    give_role(user, club, permissions=["website.manage"], name="Webseite")
    return api(user)


def url(club):
    return f"/api/orgs/{club.pk}/website/"


def custom(key, data):
    return {"key": f"c:{key}", "kind": "countdown", "on": True, "data": data}


def countdowns():
    layout = Client().get(f"/api/public/site/v1/{KEY}/").json()["home_layout"]
    return {s["key"]: s for s in layout if s.get("kind") == "countdown"}


def local(dt):
    return timezone.localtime(dt).strftime("%Y-%m-%dT%H:%M")


def test_countdown_termin_und_zeitpunkt(club, site, manager):
    start = timezone.now() + datetime.timedelta(days=5)
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
    kind = manager.get(url(club)).json()
    assert kind["home_kinds"]["countdown"] == "Countdown"
    soon = timezone.now() + datetime.timedelta(days=2)
    past = timezone.now() - datetime.timedelta(hours=1)
    sections = [
        custom(
            "t",
            {"title": "Bis zum Fest", "mode": "event", "event": fest.pk, "text": "Wir freuen uns!"},
        ),
        custom("i", {"mode": "event", "event": intern.pk}),
        custom("d", {"title": "Silvester", "mode": "date", "at": local(soon)}),
        custom("v", {"mode": "date", "at": local(past)}),
        custom(
            "x",
            {"mode": "date", "at": local(past), "after": "text", "after_text": "Es geht los!"},
        ),
    ]
    resp = manager.put(url(club), {"home_sections": sections}, "application/json")
    assert resp.status_code == 200, resp.content
    saved = {
        s["key"]: s for s in resp.json()["website"]["home_sections"] if s["key"].startswith("c:")
    }
    # interne Termine fallen weg, wie beim hervorgehobenen Termin
    assert saved["c:i"]["data"]["event"] is None
    assert saved["c:d"]["data"]["at"] == local(soon)
    assert saved["c:t"]["data"]["at"] == ""

    out = countdowns()
    assert set(out) == {"c:t", "c:d", "c:x"}
    t = out["c:t"]
    assert t["name"] == "Schützenfest" and t["text"] == "Wir freuen uns!"
    assert datetime.datetime.fromisoformat(t["target"]) == fest.starts_at
    assert t["after_text"] == ""
    assert datetime.datetime.fromisoformat(out["c:d"]["target"]).strftime(
        "%Y-%m-%dT%H:%M"
    ) == local(soon)
    assert out["c:x"]["target"] == "" and out["c:x"]["after_text"] == "Es geht los!"
    # Seitenspalte im Design „Zeitung“ wie beim hervorgehobenen Termin
    assert t["column"] == "side"


@pytest.mark.parametrize("at", ["morgen", "2026-13-01T10:00", "2026-11-14 10:00", 5])
def test_countdown_zeitpunkt_wird_geprueft(club, site, manager, at):
    resp = manager.put(
        url(club),
        {"home_sections": [custom("d", {"mode": "date", "at": at})]},
        "application/json",
    )
    assert resp.status_code == 400


def test_countdown_abgesagt_oder_begonnen(club, site):
    from website.public import SiteView

    now = timezone.now()
    with rls_bypass():
        laufend = Event.objects.create(
            organization=club,
            title="Frühschoppen",
            visibility="public",
            starts_at=now - datetime.timedelta(hours=1),
            ends_at=now + datetime.timedelta(hours=2),
        )
    view = SiteView(site)
    data = {"mode": "event", "event": laufend.pk, "after": "hide"}
    with rls_bypass():
        assert home._countdown(view, "", data) is None
        data = {**data, "after": "text", "after_text": "Läuft gerade!"}
        assert home._countdown(view, "", data)["after_text"] == "Läuft gerade!"
