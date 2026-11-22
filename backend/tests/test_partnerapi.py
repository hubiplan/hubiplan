"""API für andere Programme, Stufe 1 (docs/api.md): API-Zugänge, Schlüssel, Bereiche, Lesen.

Alle Daten erfunden.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest
from django.core import mail
from django.test import Client
from django.utils import timezone

from audit.models import AuditEntry
from core.tenancy import rls_bypass
from events.models import Event
from organizations.models import Department
from partnerapi.models import IDLE_LIFETIME, ApiAccess, hash_key

from .factories import give_role, make_member, make_user, make_website

pytestmark = pytest.mark.django_db(transaction=True)

JSON = "application/json"
BASE = "/api/partner/v1/"
ALL = [
    "einheit.lesen",
    "termine.lesen",
    "termine.mitglieder",
    "statistik.lesen",
    "vorstand.lesen",
]


@pytest.fixture
def club(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "events", "api"]
    org.save()
    return org


@pytest.fixture
def chef(club):
    user = make_user("api-vorstand@example.org", first_name="Vera", last_name="Vorstand")
    give_role(user, club)
    return user


def in_days(days: int) -> str:
    return (timezone.localdate() + datetime.timedelta(days=days)).isoformat()


def create(api, user, org, **fields):
    body = {"name": "Verbandssoftware", "scopes": ALL, "expires_at": in_days(200), **fields}
    return api(user).post(f"/api/orgs/{org.pk}/api-accesses/", json.dumps(body), JSON)


def call(key: str, path: str = "", **extra):
    return Client().get(BASE + path, HTTP_AUTHORIZATION=f"Bearer {key}", **extra)


@pytest.fixture
def key(api, chef, club) -> str:
    return create(api, chef, club).json()["key"]


def event(org, title, visibility="public", days=5, **fields):
    start = timezone.now() + datetime.timedelta(days=days)
    with rls_bypass():
        return Event.objects.create(
            organization=org,
            title=title,
            starts_at=start,
            ends_at=start + datetime.timedelta(hours=2),
            visibility=visibility,
            **fields,
        )


# --- Verwaltung ---


def test_verwaltung_nur_mit_modul_und_recht(api, orgs, club, chef):
    url = f"/api/orgs/{club.pk}/api-accesses/"
    assert api(chef).get(url).status_code == 200
    ohne = make_user("ohne-api@example.org")
    give_role(ohne, club, ["settings.view", "settings.edit"], name="Schriftführung")
    assert api(ohne).get(url).status_code == 403
    assert create(api, ohne, club).status_code == 403
    club.enabled_modules = ["members", "events"]
    club.save()
    assert api(chef).get(url).status_code == 404
    assert create(api, chef, club).status_code == 404


def test_neue_vorstandsrolle_bekommt_das_recht_nicht_von_selbst():
    from access.catalog import API_MANAGE, board_codes, codes_for

    assert API_MANAGE in codes_for("club") and API_MANAGE in codes_for("federation")
    assert API_MANAGE not in board_codes("club")
    assert API_MANAGE not in codes_for("unit")


def test_anlegen_zeigt_schluessel_einmal_protokoll_und_mail(api, club, chef):
    response = create(api, chef, club, purpose="Bestandsmeldung", recipient="Musterbund e. V.")
    assert response.status_code == 201, response.content
    data = response.json()
    key = data["key"]
    assert key.startswith("hpk_") and data["key_hint"] == key[-4:]
    assert data["state"] == "active" and data["scopes"] == ALL
    with rls_bypass():
        access = ApiAccess.objects.get(pk=data["id"])
        assert access.key_hash == hash_key(key) and key not in json.dumps(access.scopes)
        entry = AuditEntry.objects.filter(organization=club, object_type="apiaccess").latest("pk")
    assert entry.action == "create" and key not in json.dumps(entry.changes)
    listing = api(chef).get(f"/api/orgs/{club.pk}/api-accesses/").json()
    assert "key" not in listing["accesses"][0]
    assert listing["address"].endswith(BASE)
    # Dazu kommen die Bereiche mit Personendaten (Stufe 2, tests/test_partnerapi_stufe2.py)
    codes = {s["scope"]: s["personal"] for s in listing["scopes"]}
    assert set(ALL) <= set(codes) and not any(codes[c] for c in ALL)
    assert codes["mitglieder.lesen"] is True
    assert [m.to for m in mail.outbox] == [["api-vorstand@example.org"]]
    assert "Verbandssoftware" in mail.outbox[0].body and key not in mail.outbox[0].body


def test_schluessel_nur_mit_frischem_zweiten_faktor(api, club, chef, key, settings):
    settings.MFA_STEP_UP = True
    resp = create(api, chef, club)
    assert resp.status_code == 403 and resp.json().get("step_up")
    access = ApiAccess.objects.get(organization=club)
    base = f"/api/orgs/{club.pk}/api-accesses/{access.pk}/"
    for action in ("rotate/", "resume/"):
        resp = api(chef).post(base + action)
        assert resp.status_code == 403 and resp.json().get("step_up"), action
    # Ansehen, ändern und löschen gehen ohne: Sie geben nichts Neues nach außen
    assert api(chef).get(f"/api/orgs/{club.pk}/api-accesses/").status_code == 200
    assert api(chef).delete(base).status_code == 204


def test_eingaben_werden_geprueft(api, club, chef):
    assert create(api, chef, club, scopes=["gibt.es.nicht"]).status_code == 400
    assert create(api, chef, club, expires_at=in_days(-1)).status_code == 400
    assert create(api, chef, club, expires_at=in_days(500)).status_code == 400
    assert create(api, chef, club, allowed_networks=["kein-netz"]).status_code == 400
    # Im Quelltext einer fremden Webseite stehen keine Schlüssel für Mitgliedertermine
    assert create(api, chef, club, embeddable=True).status_code == 400
    ok = create(api, chef, club, embeddable=True, scopes=["termine.lesen"])
    assert ok.status_code == 201
    # Vorausgesetztes kommt mit; Bereiche abgeschalteter Module gibt es nicht
    nur = create(api, chef, club, scopes=["termine.mitglieder", "ergebnisse.lesen"]).json()
    assert nur["scopes"] == ["termine.lesen", "termine.mitglieder"]


def test_aendern_verlaengern_loeschen(api, club, chef, key):
    with rls_bypass():
        access = ApiAccess.objects.get()
    url = f"/api/orgs/{club.pk}/api-accesses/{access.pk}/"
    body = {"name": "Verband neu", "scopes": ["einheit.lesen"], "expires_at": in_days(300)}
    changed = api(chef).patch(url, json.dumps(body), JSON)
    assert changed.status_code == 200, changed.content
    assert changed.json()["scopes"] == ["einheit.lesen"] and changed.json()["name"] == "Verband neu"
    assert call(key, "events/").status_code == 403
    assert api(chef).delete(url).status_code == 204
    assert call(key).status_code == 401
    with rls_bypass():
        actions = list(
            AuditEntry.objects.filter(organization=club, object_type="apiaccess")
            .order_by("pk")
            .values_list("action", flat=True)
        )
    assert actions == ["create", "update", "delete"]


def test_fremde_einheit_sieht_und_aendert_nichts(api, orgs, club, chef, board_b, key):
    with rls_bypass():
        access = ApiAccess.objects.get()
    orgs["b"].enabled_modules = ["members", "events", "api"]
    orgs["b"].save()
    assert api(board_b).get(f"/api/orgs/{orgs['b'].pk}/api-accesses/").json()["accesses"] == []
    other = f"/api/orgs/{orgs['b'].pk}/api-accesses/{access.pk}/"
    assert api(board_b).delete(other).status_code == 404
    assert api(board_b).get(f"/api/orgs/{club.pk}/api-accesses/").status_code == 404


# --- Schlüssel ---


def test_ohne_oder_mit_falschem_schluessel_401(club):
    for response in (Client().get(BASE), call("hpk_falsch"), call("hpm_anderer-schluessel")):
        assert response.status_code == 401
        assert response["Content-Type"].startswith("application/problem+json")
        assert response.json()["code"] == "invalid_key"
        assert response["WWW-Authenticate"].startswith("Bearer")


def test_selbstauskunft(club, key):
    response = call(key)
    assert response.status_code == 200, response.content
    data = response.json()
    assert data["unit"] == {"id": str(club.uuid), "name": "Verein A", "type": "club"}
    assert [s["scope"] for s in data["access"]["scopes"]] == ALL
    assert data["api_version"] == "1" and data["access"]["limits"]["requests_per_hour"] == 600
    assert response["Cache-Control"] == "private, no-store"
    assert "Access-Control-Allow-Origin" not in response
    with rls_bypass():
        access = ApiAccess.objects.get()
    assert access.request_count == 1 and access.last_used_at is not None
    assert access.last_used_ip == "127.0.0.1"


def test_schluessel_gilt_nur_unter_der_api(api, club, key):
    assert Client().get(
        f"/api/orgs/{club.pk}/", HTTP_AUTHORIZATION=f"Bearer {key}"
    ).status_code in (
        401,
        403,
    )
    assert Client().get(
        f"/api/orgs/{club.pk}/api-accesses/", HTTP_AUTHORIZATION=f"Bearer {key}"
    ).status_code in (401, 403)


def test_fehlender_bereich_403(api, club, chef):
    key = create(api, chef, club, scopes=["einheit.lesen"]).json()["key"]
    response = call(key, "events/")
    assert response.status_code == 403
    assert response.json()["code"] == "missing_scope"
    assert response.json()["scope"] == "termine.lesen"
    assert call(key, "unit/").status_code == 200


def test_abgelaufen_ruhend_wieder_einschalten(api, club, chef, key):
    with rls_bypass():
        access = ApiAccess.objects.get()
        ApiAccess.objects.filter(pk=access.pk).update(
            active_since=timezone.now() - IDLE_LIFETIME - datetime.timedelta(days=1),
            last_used_at=None,
        )
    assert call(key).json()["code"] == "access_idle"
    url = f"/api/orgs/{club.pk}/api-accesses/{access.pk}/"
    assert api(chef).get(f"/api/orgs/{club.pk}/api-accesses/").json()["accesses"][0]["state"] == (
        "idle"
    )
    assert api(chef).post(f"{url}resume/").json()["state"] == "active"
    assert call(key).status_code == 200
    with rls_bypass():
        ApiAccess.objects.filter(pk=access.pk).update(
            expires_at=timezone.now() - datetime.timedelta(minutes=1)
        )
    expired = call(key)
    assert expired.status_code == 401 and expired.json()["code"] == "access_expired"
    body = {"expires_at": in_days(100)}
    assert api(chef).patch(url, json.dumps(body), JSON).json()["state"] == "active"
    assert call(key).status_code == 200


def test_neuer_schluessel_alter_gilt_noch_sieben_tage(api, club, chef, key):
    with rls_bypass():
        access = ApiAccess.objects.get()
    mail.outbox.clear()
    rotated = api(chef).post(f"/api/orgs/{club.pk}/api-accesses/{access.pk}/rotate/")
    assert rotated.status_code == 200
    new = rotated.json()["key"]
    assert new != key and rotated.json()["previous_until"]
    assert call(new).status_code == 200 and call(key).status_code == 200
    assert len(mail.outbox) == 1 and new not in mail.outbox[0].body
    with rls_bypass():
        ApiAccess.objects.filter(pk=access.pk).update(
            previous_until=timezone.now() - datetime.timedelta(seconds=1)
        )
    assert call(key).status_code == 401 and call(new).status_code == 200


def test_erlaubte_adressen(api, club, chef):
    key = create(api, chef, club, allowed_networks=["203.0.113.0/24"]).json()["key"]
    blocked = call(key)
    assert blocked.status_code == 403 and blocked.json()["code"] == "ip_not_allowed"
    assert call(key, REMOTE_ADDR="203.0.113.9").status_code == 200


def test_modul_aus_oder_instanz_aus(club, key, settings):
    club.enabled_modules = ["members", "events"]
    club.save()
    assert call(key).status_code == 401
    club.enabled_modules = ["members", "events", "api"]
    club.save()
    assert call(key).status_code == 200
    settings.PARTNER_API_ENABLED = False
    assert call(key).status_code == 404
    assert Client().get(f"{BASE}openapi.json").status_code == 404


def test_bereich_eines_abgeschalteten_moduls_ruht(club, key):
    assert call(key, "events/").status_code == 200
    club.enabled_modules = ["members", "api"]
    club.save()
    response = call(key, "events/")
    assert response.status_code == 403 and response.json()["code"] == "missing_scope"


def test_grenze_je_zugang(club, key, monkeypatch):
    from partnerapi import views

    monkeypatch.setattr(views, "ACCESS_LIMIT", 2)
    assert call(key).status_code == 200 and call(key).status_code == 200
    limited = call(key)
    assert limited.status_code == 429 and limited.json()["code"] == "too_many_requests"
    assert int(limited["Retry-After"]) > 0


def test_aus_fremden_webseiten_aufrufbar(api, club, chef):
    key = create(api, chef, club, embeddable=True, scopes=["termine.lesen"]).json()["key"]
    assert call(key, "events/")["Access-Control-Allow-Origin"] == "*"
    preflight = Client().options(f"{BASE}events/")
    assert preflight.status_code == 204
    assert "Authorization" in preflight["Access-Control-Allow-Headers"]


# --- Daten ---


def test_einheit_und_untereinheiten(club, key):
    with rls_bypass():
        zug = Department.objects.create(organization=club, parent=club, name="Jägerzug")
        Department.objects.create(organization=club, parent=zug, name="Gruppe 1")
        Department.objects.create(organization=club, parent=club, name="Aufgelöst", is_active=False)
    unit = call(key, "unit/").json()
    assert unit["name"] == "Verein A" and unit["city"] == "Musterstadt"
    assert unit["founding_year"] == 1900 and unit["logo_url"] is None
    assert call(key, "unit/logo").status_code == 404
    units = call(key, "units/").json()["units"]
    by_name = {u["name"]: u for u in units}
    assert set(by_name) == {"Jägerzug", "Gruppe 1"}
    assert by_name["Jägerzug"]["parent"] is None
    assert by_name["Gruppe 1"]["parent"] == by_name["Jägerzug"]["id"] == str(zug.uuid)


def test_termine_nach_sichtbarkeit(api, orgs, club, chef, key):
    event(club, "Sommerfest")
    event(club, "Mitgliederabend", "members", days=6)
    event(club, "Vorstandssitzung", "board", days=7)
    event(club, "Aus dem Verbund", days=8, remote_uid="fern-1")
    event(orgs["b"], "Fest bei Verein B")
    titles = [e["title"] for e in call(key, "events/").json()["events"]]
    assert titles == ["Sommerfest", "Mitgliederabend"]
    public = create(api, chef, club, scopes=["termine.lesen"]).json()["key"]
    data = call(public, "events/").json()
    assert [e["title"] for e in data["events"]] == ["Sommerfest"]
    entry = data["events"][0]
    assert entry["visibility"] == "public" and entry["unit"] is None and not entry["recurring"]
    assert entry["id"].startswith(entry["event_id"] + "-") and data["next_cursor"] is None


def test_termine_serie_zeitraum_und_blaettern(club, key):
    event(club, "Training", days=1, repeat="weekly")
    data = call(key, f"events/?to={in_days(30)}&limit=2").json()
    assert len(data["events"]) == 2 and data["next_cursor"]
    assert all(e["recurring"] and e["title"] == "Training" for e in data["events"])
    rest = call(key, f"events/?to={in_days(30)}&limit=2&cursor={data['next_cursor']}").json()
    ids = [e["id"] for e in data["events"] + rest["events"]]
    assert len(ids) == len(set(ids)) == 4
    assert call(key, f"events/?from={in_days(10)}&to={in_days(2)}").status_code == 400
    assert call(key, "events/?from=gestern").status_code == 400
    assert call(key, f"events/?to={in_days(900)}").json()["code"] == "invalid_request"


def test_zugang_fuer_eine_untereinheit(api, club, chef):
    with rls_bypass():
        zug = Department.objects.create(organization=club, parent=club, name="Jägerzug")
        gruppe = Department.objects.create(organization=club, parent=zug, name="Gruppe 1")
        andere = Department.objects.create(organization=club, parent=club, name="Schützenzug")
    event(club, "Vereinsfest")
    event(club, "Zugabend", department=zug, days=6)
    event(club, "Gruppenabend", "members", department=gruppe, days=7)
    event(club, "Fremder Zug", department=andere, days=8)
    made = create(api, chef, club, unit=zug.pk, scopes=[*ALL, "vorstand.lesen"])
    assert made.status_code == 201, made.content
    # „Vorstand lesen“ gibt es für einen Zugang einer Untereinheit nicht
    assert "vorstand.lesen" not in made.json()["scopes"]
    assert made.json()["unit"] == {"id": zug.pk, "name": "Jägerzug"}
    key = made.json()["key"]
    assert call(key).json()["unit"] == {"id": str(zug.uuid), "name": "Jägerzug", "type": "unit"}
    assert call(key, "unit/").json()["name"] == "Jägerzug"
    assert [u["name"] for u in call(key, "units/").json()["units"]] == ["Gruppe 1"]
    titles = [e["title"] for e in call(key, "events/").json()["events"]]
    assert titles == ["Zugabend", "Gruppenabend"]
    assert call(key, "board/").status_code == 403
    assert create(api, chef, club, unit=999999).status_code == 400
    # Filter nach Untereinheit beim Zugang des Vereins
    club_key = create(api, chef, club).json()["key"]
    filtered = call(club_key, f"events/?unit={gruppe.uuid}").json()["events"]
    assert [e["title"] for e in filtered] == ["Gruppenabend"]
    assert call(club_key, "events/?unit=00000000-0000-0000-0000-000000000000").status_code == 404


def test_mitgliederzahlen_ohne_personen(club, key):
    make_member(club, "Erika", "Muster", birth_date=datetime.date(1980, 5, 17))
    make_member(club, "Max", "Beispiel", birth_date=datetime.date(2012, 3, 1))
    response = call(key, "statistics/census/")
    assert response.status_code == 200, response.content
    data = response.json()
    assert data["total"] == 2 and data["persons"] == 2 and data["ages"] == "sport"
    assert sum(row["total"] for row in data["rows"]) == 2
    text = response.content.decode()
    assert "Muster" not in text and "Erika" not in text and "places" not in data
    assert call(key, "statistics/census/?ages=unbekannt").status_code == 400
    earlier = call(key, "statistics/census/?date=2010-01-01&ages=zehn").json()
    assert earlier["total"] == 0 and earlier["date"] == "2010-01-01"


def test_vorstand_ohne_oeffentliche_webseite_nur_rollen(club, key):
    from access.models import Role

    with rls_bypass():
        Role.objects.filter(organization=club, name="Vorstand").update(
            on_website=True, contact_email="vorstand@example.org"
        )
    data = call(key, "board/").json()
    assert data == {
        "names_published": False,
        "roles": [{"role": "Vorstand", "email": "vorstand@example.org", "holders": []}],
    }
    assert "Vera" not in json.dumps(data)


def test_veroeffentlichtes_nur_mit_oeffentlicher_webseite(api, club, chef):
    club.enabled_modules = ["members", "events", "api", "website", "competitions"]
    club.save()
    key = create(
        api, chef, club, scopes=["ergebnisse.lesen", "dokumente.lesen", "vorstand.lesen"]
    ).json()["key"]
    assert call(key, "results/").json() == {
        "published": False,
        "competitions": [],
        "next_cursor": None,
    }
    assert call(key, "documents/").json() == {"published": False, "documents": []}
    assert call(key, "results/unbekannt/").status_code == 404
    make_website(club, public_key="api-a", state="public")
    assert call(key, "results/").status_code == 200
    assert call(key, "documents/").status_code == 200
    assert call(key, "board/").json()["names_published"] in (True, False)


# --- Beschreibung ---


def test_openapi_ohne_anmeldung_und_kopie_aktuell(club):
    from drf_spectacular.drainage import GENERATOR_STATS

    from partnerapi import openapi
    from partnerapi.management.commands.api_openapi import text

    openapi.build.cache_clear()
    GENERATOR_STATS.reset()
    with GENERATOR_STATS.silence():
        schema = openapi.build()
    assert not GENERATOR_STATS._error_cache and not GENERATOR_STATS._warn_cache
    response = Client().get(f"{BASE}openapi.json")
    assert response.status_code == 200
    served = response.json()
    assert served["paths"].keys() == schema["paths"].keys()
    assert "/api/partner/v1/events/" in served["paths"]
    for operations in served["paths"].values():
        for operation in operations.values():
            assert operation["security"] == [{"apiKey": []}]
    assert "Event" in served["components"]["schemas"]
    copy = Path(openapi.__file__).with_name("openapi.json")
    assert copy.read_text(encoding="utf-8") == text(), (
        "partnerapi/openapi.json ist veraltet: im Ordner backend "
        "„python manage.py api_openapi partnerapi/openapi.json“ ausführen"
    )


def test_lesbare_beschreibung_ohne_anmeldung(club, settings):
    from partnerapi import docs_page

    docs_page.render.cache_clear()
    response = Client().get(f"{BASE}docs/")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    assert "default-src 'none'" in response["Content-Security-Policy"]
    page = response.content.decode()
    assert "<h1>HUBIplan API für andere Programme</h1>" in page
    assert "/api/partner/v1/events/" in page
    assert "termine.schreiben" in page
    assert 'id="schema-Event"' in page
    assert 'href="../openapi.json"' in page
    # nichts von fremden Servern, kein Skript
    assert "<script" not in page and "src=" not in page
    english = Client().get(f"{BASE}docs/?lang=en").content.decode()
    assert "<h1>HUBIplan API for other programs</h1>" in english
    by_header = Client().get(f"{BASE}docs/", HTTP_ACCEPT_LANGUAGE="en-GB,en;q=0.8")
    assert by_header.content.decode() == english
    settings.PARTNER_API_ENABLED = False
    assert Client().get(f"{BASE}docs/").status_code == 404


def test_erinnerung_vor_dem_ablauf_einmal(api, club, chef, key):
    from partnerapi.tasks import remind_expiring

    mail.outbox.clear()
    assert remind_expiring() == 0
    with rls_bypass():
        ApiAccess.objects.update(expires_at=timezone.now() + datetime.timedelta(days=10))
    assert remind_expiring() == 1
    assert remind_expiring() == 0
    assert len(mail.outbox) == 1 and "läuft bald ab" in mail.outbox[0].subject
    # Verlängern: vor dem neuen Ablauf wird wieder erinnert
    with rls_bypass():
        access = ApiAccess.objects.get()
    url = f"/api/orgs/{club.pk}/api-accesses/{access.pk}/"
    api(chef).patch(url, json.dumps({"expires_at": in_days(20)}), JSON)
    assert remind_expiring() == 1
