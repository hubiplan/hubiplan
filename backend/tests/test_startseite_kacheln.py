"""Kacheln der Startseite bei Anlass (hometiles): Auswahl „bei Anlass / immer / nie“, Anlässe
und Rechte. Nur erfundene Daten."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from core.tenancy import rls_bypass, tenant_context
from finance.models import Account

from .factories import give_role, make_member, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


def tiles(client, url) -> dict:
    resp = client.get(url)
    assert resp.status_code == 200, resp.content
    return {t["key"]: t for t in resp.json()["tiles"]}


def put(client, url, key, state):
    return client.put(url, {"key": key, "state": state}, content_type=JSON)


@pytest.fixture
def club(orgs):
    org = orgs["a"]
    org.enabled_modules = sorted({*org.enabled_modules, "finance", "members", "pinboard", "portal"})
    org.member_portal_enabled = True
    org.save()
    return org


def test_vorstand_bekommt_kacheln_standardmaessig_bei_anlass(api, club, board_a, monkeypatch):
    make_member(club, "Erika", "Muster", entry_date=datetime.date(2026, 3, 1))
    c = api(board_a)
    url = f"/api/orgs/{club.pk}/home-tiles/"
    monkeypatch.setattr("hometiles.org_tiles.today", lambda: datetime.date(2026, 6, 10))
    data = tiles(c, url)
    # Jede Kachel, die der Vorstand haben darf, liefert Inhalt (kein Fehler beim Aufbau)
    assert {"kasse", "verein-zahlen", "umfragen-pinnwand"} <= set(data)
    assert all(t["content"] is not None for t in data.values()), data
    zahlen = data["verein-zahlen"]
    assert zahlen["state"] == "auto"
    # Im Juni kein Anlass: nicht zu sehen, Inhalt trotzdem da (für „Anpassen“)
    assert zahlen["urgent"] is False and zahlen["shown"] is False
    assert zahlen["content"]["figures"][0] == {"label": "Mitglieder", "value": "1", "tone": None}
    # Im Januar steht die Stichtagsmeldung an: Kachel erscheint von selbst
    monkeypatch.setattr("hometiles.org_tiles.today", lambda: datetime.date(2027, 1, 10))
    zahlen = tiles(c, url)["verein-zahlen"]
    assert zahlen["urgent"] is True and zahlen["shown"] is True
    assert zahlen["content"]["reason"] == "Die Stichtagsmeldung steht an."


def test_auswahl_immer_und_nie(api, club, board_a, monkeypatch):
    monkeypatch.setattr("hometiles.org_tiles.today", lambda: datetime.date(2027, 1, 10))
    c = api(board_a)
    url = f"/api/orgs/{club.pk}/home-tiles/"
    # „nie“ schlägt den Anlass und spart den Inhalt
    data = put(c, url, "verein-zahlen", "off").json()
    zahlen = next(t for t in data["tiles"] if t["key"] == "verein-zahlen")
    assert zahlen["state"] == "off" and zahlen["shown"] is False and zahlen["content"] is None
    board_a.refresh_from_db()
    assert board_a.home_layout[f"o{club.pk}"]["hidden"] == ["verein-zahlen"]
    # „immer“ zeigt auch ohne Anlass
    monkeypatch.setattr("hometiles.org_tiles.today", lambda: datetime.date(2026, 6, 10))
    assert put(c, url, "verein-zahlen", "on").status_code == 200
    zahlen = tiles(c, url)["verein-zahlen"]
    assert zahlen["state"] == "on" and zahlen["shown"] is True
    board_a.refresh_from_db()
    layout = board_a.home_layout[f"o{club.pk}"]
    assert layout["shown"] == ["verein-zahlen"] and layout["hidden"] == []
    # Die Anordnung im Browser behält die Wahl, auch wenn eine ältere Fassung ohne „shown“ speichert
    c.put(
        "/api/me/home-actions/",
        {"layout": {f"o{club.pk}": {"order": ["termine"], "hidden": [], "wide": []}}},
        content_type=JSON,
    )
    assert tiles(c, url)["verein-zahlen"]["state"] == "on"
    # Zurück auf „bei Anlass“
    put(c, url, "verein-zahlen", "auto")
    assert tiles(c, url)["verein-zahlen"]["state"] == "auto"
    # Unbekannte Kachel, falscher Zustand
    assert put(c, url, "gibt-es-nicht", "on").status_code == 404
    assert put(c, url, "verein-zahlen", "vielleicht").status_code == 400


def test_kasse_im_minus_und_nur_mit_recht(api, club, board_a):
    with rls_bypass(), tenant_context(club.pk):
        Account.objects.create(
            organization=club,
            name="Girokonto",
            kind="bank",
            opening_date=datetime.date(2020, 1, 1),
            opening_balance=Decimal("-25.00"),
        )
    kasse = tiles(api(board_a), f"/api/orgs/{club.pk}/home-tiles/")["kasse"]
    assert kasse["shown"] is True
    assert kasse["content"]["reason"] == "Ein Konto steht im Minus."
    assert kasse["content"]["figures"][0]["label"] == "Girokonto"
    assert kasse["content"]["figures"][0]["tone"] == "bad"
    # Ohne Finanzrechte keine Kasse und keine Zahlen zum Verein
    schreiber = make_user("schreiber@example.org")
    give_role(schreiber, club, permissions=["events.view"], name="Schriftführung")
    data = tiles(api(schreiber), f"/api/orgs/{club.pk}/home-tiles/")
    assert "kasse" not in data and "verein-zahlen" not in data


def test_mitglied_pinnwand_bei_neuen_beitraegen(api, club):
    from pinboard.models import Notice
    from portal.models import PortalAccess

    m = make_member(club, "Anna", "Beispiel")
    user = make_user("anna-konto@example.org")
    with rls_bypass():
        access = PortalAccess.objects.create(organization=club, membership=m, user=user)
    c = api(user)
    url = f"/api/portal/{access.pk}/home-tiles/"
    pin = tiles(c, url)["pinnwand"]
    assert pin["shown"] is False and pin["content"]["reason"] == ""
    with rls_bypass(), tenant_context(club.pk):
        Notice.objects.create(organization=club, text="Arbeitseinsatz am Samstag\nBitte Handschuhe")
    pin = tiles(c, url)["pinnwand"]
    assert pin["shown"] is True
    assert pin["content"]["rows"][0]["title"] == "Arbeitseinsatz am Samstag"
    # Eigene Wahl gilt im Bereich des Zugangs
    put(c, url, "pinnwand", "off")
    user.refresh_from_db()
    assert user.home_layout[f"p{access.pk}"]["hidden"] == ["pinnwand"]
    # Fremder Zugang: nicht zu finden
    other = make_user("fremd@example.org")
    assert api(other).get(url).status_code == 404


def test_app_pfad_vorhanden(club):
    assert reverse("app-admin-home-tiles", kwargs={"org_id": club.pk}).endswith(
        f"/admin/u/{club.pk}/home-tiles/"
    )
