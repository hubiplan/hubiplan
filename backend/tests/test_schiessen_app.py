"""Schießen in der Android-App (konzepte/schiessen-android.md): Standzugang aus der
Verwaltung der App, Schießmeister ohne „Wettbewerbe bearbeiten“, Ranglisten für Mitglieder
wie auf der Webseite. Alles erfunden."""
# ruff: noqa: F811  (Fixtures als Parameter)

import datetime
from decimal import Decimal

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.test import Client

from competitions.models import Competition, Score, Scoring, StandAccess, Starter
from website.models import Website

from .factories import give_role, make_member
from .test_app_devices import APP, app, pair, pairing_code
from .test_app_verwaltung import unlock
from .test_m12_events import JSON, cal, member_with_access  # noqa: F401

pytestmark = pytest.mark.django_db
ADMIN = f"{APP}admin/u/"


@pytest.fixture
def verein(cal):
    club = cal["a"]
    club.enabled_modules = [*club.enabled_modules, "competitions", "website"]
    club.save()
    comp = Competition.objects.create(
        organization=club,
        title="Preisschießen 2027",
        date=datetime.date.today(),
        status="laeuft",
        website="live",
        website_depth="top3",
    )
    einzel = Scoring.objects.create(
        organization=club, competition=comp, name="Einzel", prize_places=1
    )
    for first, value in (("Max", 30), ("Erika", 28)):
        m = make_member(club, first, "Muster")
        s = Starter.objects.create(
            organization=club, competition=comp, membership=m, name=f"{first} Muster"
        )
        Score.objects.create(organization=club, scoring=einzel, starter=s, value=Decimal(value))
    return {"club": club, "comp": comp}


@pytest.fixture
def schiessmeister(verein, api):
    """Nur „Ergebnisse erfassen“, mit App und 2FA."""
    from django.core.cache import cache

    cache.clear()
    _, user, _ = member_with_access(verein["club"], "Sascha")
    give_role(user, verein["club"], ["competitions.results"], name="Schießmeister")
    secret = generate_totp_secret()
    TOTP.activate(user, secret)
    resp = pair(pairing_code(api(user)))
    assert resp.status_code == 201, resp.json()
    info = {"user": user, "token": resp.json()["token"], "secret": secret}
    resp = unlock(info)
    assert resp.status_code == 201, resp.json()
    info["admin"] = resp.json()["token"]
    return info


class TestStandzugangInDerApp:
    def test_ueberblick_zeigt_wettbewerbe(self, verein, schiessmeister):
        data = app(schiessmeister["token"]).get(f"{APP}admin/").json()
        unit = next(u for u in data["units"] if u["id"] == verein["club"].pk)
        assert "competitions.results" in unit["permissions"]
        assert "competitions" in unit["modules"]

    def test_anlegen_nutzen_beenden(self, verein, schiessmeister):
        c = app(schiessmeister["admin"])
        base = f"{ADMIN}{verein['club'].pk}/competitions/"
        listing = c.get(base)
        assert listing.status_code == 200, listing.json()
        assert [x["title"] for x in listing.json()] == ["Preisschießen 2027"]
        comp_id = verein["comp"].pk
        detail = c.get(f"{base}{comp_id}/").json()
        assert detail["can_manage"] is False and detail["can_stand_access"] is True
        # Nur lesen: anlegen oder ändern geht in der App nicht
        assert c.post(base, {"title": "Neu"}, content_type=JSON).status_code == 405
        resp = c.post(f"{base}{comp_id}/stand-access/", {"label": "Handy"}, content_type=JSON)
        assert resp.status_code == 201, resp.json()
        token, access_id = resp.json()["token"], resp.json()["id"]
        access = StandAccess.objects.get(pk=access_id)
        assert access.token_hash != token
        assert Client().get(f"/api/public/stand/{token}/").status_code == 200
        assert c.delete(f"{base}{comp_id}/stand-access/{access_id}/").status_code == 204
        assert Client().get(f"/api/public/stand/{token}/").status_code == 404

    def test_ohne_vorstandsschluessel_nicht(self, verein, schiessmeister):
        base = f"{ADMIN}{verein['club'].pk}/competitions/"
        resp = app(schiessmeister["token"], with_device=False).get(base)
        assert resp.status_code in (401, 403)

    def test_nur_lesen_reicht_nicht(self, verein, api):
        _, user, _ = member_with_access(verein["club"], "Lukas")
        give_role(user, verein["club"], ["competitions.view"], name="Nur lesen")
        resp = api(user).post(
            f"/api/orgs/{verein['club'].pk}/competitions/{verein['comp'].pk}/stand-access/",
            {},
            format="json",
        )
        assert resp.status_code == 403


class TestRanglistenFuerMitglieder:
    def test_wie_auf_der_webseite(self, verein, api):
        # Webseite noch auf der Wartungsseite: Mitglieder sehen die Ergebnisse trotzdem
        site = Website.objects.create(
            organization=verein["club"],
            public_key="schluessel-a",
            state="maintenance",
            name_format="initial",
        )
        _, user, access = member_with_access(verein["club"], "Mia")
        c = api(user)
        base = f"/api/portal/{access.pk}/rankings/"
        # Baustein „Ergebnisse“ aus: nichts
        site.blocks = {"results": False}
        site.save()
        assert c.get(base).json()["competitions"] == []
        site.blocks = {"results": True}
        site.save()
        data = c.get(base).json()
        assert [x["title"] for x in data["competitions"]] == ["Preisschießen 2027"]
        assert "url" not in data["competitions"][0]
        token = data["competitions"][0]["id"]
        detail = c.get(f"{base}{token}/").json()
        rows = detail["scorings"][0]["rows"]
        # Nur Preisplätze (hier einer), wie auf der Webseite
        assert [r["place"] for r in rows] == [1]
        assert rows[0]["name"] == "Max M." and detail["poll_seconds"] == 15
        assert "version_url" not in detail
        assert "version" in c.get(f"{base}{token}/?version=1").json()
        verein["comp"].website = "aus"
        verein["comp"].save()
        assert c.get(f"{base}{token}/").status_code == 404

    def test_fremder_zugang_nicht(self, verein, api):
        _, user, _ = member_with_access(verein["club"], "Mia")
        _, other, other_access = member_with_access(verein["club"], "Otto")
        assert api(user).get(f"/api/portal/{other_access.pk}/rankings/").status_code == 404
