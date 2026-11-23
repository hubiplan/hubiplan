"""Köderdaten (Härtung B2): unsichtbar für Vereine, Alarm bei Benutzung."""

from __future__ import annotations

import json
from email.message import EmailMessage

import pytest
from django.core import mail
from django.test import Client

from circulars import inbound
from core.tenancy import rls_bypass
from organizations import decoys
from organizations.models import DecoyHit, Organization

from .conftest import csrf_headers
from .factories import give_role, make_member, make_user

JSON = "application/json"
URL = "/api/platform/decoys/"
AUTH = "/_allauth/browser/v1"
DOMAIN = "verteiler.example"


@pytest.fixture
def platform_admin(db):
    user = make_user("plattform@example.org")
    give_role(user, Organization.platform())
    return user


@pytest.fixture(autouse=True)
def _verteiler_domain(settings):
    settings.INBOUND_DOMAINS = [DOMAIN]
    settings.SECURITY_ALERTS = True
    settings.SECURITY_ALERT_EMAIL = "betreiber@example.org"


@pytest.fixture
def koeder(db, platform_admin):
    """Ein Köder; die Alarm-Mails des Anlegens (neuer Plattformzugang) sind weg."""
    pk = decoys.create()
    mail.outbox.clear()
    return next(d for d in decoys.state()["decoys"] if d["id"] == pk)


def hits() -> list[DecoyHit]:
    with rls_bypass():
        return list(DecoyHit.objects.order_by("id"))


def alarme() -> list:
    return [m for m in mail.outbox if "Köderdaten" in m.subject]


def test_anlegen_nur_plattform(api, orgs, board_a, platform_admin):
    assert Client().get(URL).status_code in (401, 403)
    assert api(board_a).get(URL).status_code == 403
    assert api(board_a).post(URL, {}, content_type=JSON).status_code == 403
    client = api(platform_admin)
    stand = client.get(URL).json()
    assert stand == {"decoys": [], "limit": 5, "domain": DOMAIN, "hits": []}
    stand = client.post(URL, {}, content_type=JSON).json()
    (eintrag,) = stand["decoys"]
    assert eintrag["email"].endswith(f"@{DOMAIN}") and " " in eintrag["name"]
    # eigene Adresse; ein Konto oder ein vorhandener Köder taugt nicht
    assert client.post(URL, {"email": "kein-at"}, content_type=JSON).status_code == 400
    assert client.post(URL, {"email": board_a.email}, content_type=JSON).status_code == 400
    assert client.post(URL, {"email": eintrag["email"]}, content_type=JSON).status_code == 400
    stand = client.post(URL, {"email": "Lockvogel@postfach.example"}, content_type=JSON).json()
    assert [d["email"] for d in stand["decoys"]][1] == "lockvogel@postfach.example"
    for _ in range(3):
        assert client.post(URL, {}, content_type=JSON).status_code == 201
    assert client.post(URL, {}, content_type=JSON).status_code == 400  # höchstens fünf
    stand = client.delete(f"{URL}{eintrag['id']}/").json()
    assert len(stand["decoys"]) == 4
    assert decoys.decoy_for_address(eintrag["email"]) is None
    assert not alarme()
    assert not hits()


def test_ohne_verteiler_domain_nur_mit_eigener_adresse(api, platform_admin, settings):
    settings.INBOUND_DOMAINS = []
    client = api(platform_admin)
    assert client.get(URL).json()["domain"] == ""
    assert client.post(URL, {}, content_type=JSON).status_code == 400
    antwort = client.post(URL, {"email": "falle@postfach.example"}, content_type=JSON)
    assert antwort.status_code == 201


def test_kein_verein_sieht_den_koeder(api, orgs, board_a, koeder, platform_admin):
    erika = make_member(orgs["a"], "Erika", "Musterfrau")
    nachname = koeder["name"].split(" ")[-1]
    federation = make_user("verband@example.org")
    give_role(federation, orgs["federation"])
    for user, org in ((board_a, orgs["a"]), (federation, orgs["federation"])):
        client = api(user)
        for pfad in ("members/", f"members/?search={nachname}", "members/export/?als=csv"):
            antwort = client.get(f"/api/orgs/{org.pk}/{pfad}")
            text = (
                b"".join(antwort.streaming_content)
                if getattr(antwort, "streaming", False)
                else antwort.content
            ).decode("utf-8", "replace")
            assert koeder["email"] not in text and koeder["name"] not in text, pfad
    liste = api(board_a).get(f"/api/orgs/{orgs['a'].pk}/members/").json()
    zeilen = liste["results"] if isinstance(liste, dict) else liste
    assert [z["id"] for z in zeilen] == [erika.pk]
    # Die Plattform hat keinen Mitgliederbereich, auch nicht für ihre Verwaltung
    platform = Organization.platform().pk
    assert api(platform_admin).get(f"/api/orgs/{platform}/members/").status_code in (403, 404)
    assert not hits()


def test_abruf_der_nummer_loest_aus(api, orgs, board_a, koeder):
    erika = make_member(orgs["a"], "Erika", "Musterfrau")
    client = api(board_a)
    assert client.get(f"/api/orgs/{orgs['a'].pk}/members/{erika.pk}/").status_code == 200
    assert not hits()
    for _ in range(2):
        assert client.get(f"/api/orgs/{orgs['a'].pk}/members/{koeder['id']}/").status_code == 404
    (eintrag,) = hits()
    assert (eintrag.kind, eintrag.membership_id, eintrag.count) == ("lookup", koeder["id"], 2)
    assert board_a.email in eintrag.detail and "/members/" in eintrag.detail
    (alarm,) = alarme()  # eine Mail je Stunde und Art
    assert "Abruf" in alarm.subject and koeder["email"] not in alarm.body


def test_anmeldung_und_passwort_vergessen_loesen_aus(db, koeder):
    client = Client(enforce_csrf_checks=True)
    antwort = client.post(
        f"{AUTH}/auth/login",
        {"email": koeder["email"].upper(), "password": "geraten"},
        content_type=JSON,
        headers=csrf_headers(client),
    )
    assert antwort.status_code in (400, 401)
    client.post(
        f"{AUTH}/auth/password/request",
        {"email": koeder["email"]},
        content_type=JSON,
        headers=csrf_headers(client),
    )
    (eintrag,) = hits()
    assert (eintrag.kind, eintrag.count) == ("login", 2)
    assert len(alarme()) == 1
    # andere Adressen und Unsinn lösen nichts aus
    for body in (json.dumps({"email": "wer@example.org", "password": "x"}), "kein json", "[]"):
        client.post(f"{AUTH}/auth/login", body, content_type=JSON, headers=csrf_headers(client))
    assert len(hits()) == 1


def eingang(to: str, sender: str = "fremd@example.net") -> bytes:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = "Ihr Gewinn wartet"
    msg["Message-ID"] = f"<{abs(hash(to))}@example.net>"
    msg.set_content("Hallo")
    return msg.as_bytes()


def test_mail_an_die_koederadresse_loest_aus(db, koeder):
    eintrag = inbound.process_message(eingang(f"Vorname Name <{koeder['email']}>"))
    # im Protokoll des Sammelpostfachs steht nichts, was den Köder verrät
    assert eintrag.reason == "Kein Verteiler unter dieser Adresse."
    (treffer,) = hits()
    assert treffer.kind == "mail_in" and treffer.membership_id == koeder["id"]
    assert "fremd@example.net" in treffer.detail and "Gewinn" in treffer.detail
    assert len(alarme()) == 1
    inbound.process_message(eingang(f"niemand@{DOMAIN}"))
    assert len(hits()) == 1


def test_eigene_mail_an_den_koeder_wird_nicht_versendet(db, koeder, settings):
    from outbox.mail import send
    from outbox.models import OutgoingMail

    settings.EMAIL_BACKEND = "outbox.backend.OutboxBackend"
    send([koeder["email"]], "Einladung zum Sommerfest", "Text")
    with rls_bypass():
        ausgang = list(OutgoingMail.objects.order_by("id"))
    # nur der Alarm an den Betreiber steht im Postausgang
    (alarm,) = ausgang
    assert alarm.to == "betreiber@example.org" and "Köderdaten" in alarm.subject
    (treffer,) = hits()
    assert treffer.kind == "mail_out" and "Sommerfest" in treffer.detail


def test_ausloesungen_zeigen_und_leeren(api, orgs, board_a, koeder, platform_admin):
    api(board_a).get(f"/api/orgs/{orgs['a'].pk}/members/{koeder['id']}/")
    client = api(platform_admin)
    (eintrag,) = client.get(URL).json()["hits"]
    assert eintrag["kind"] == "lookup" and eintrag["decoy"] == koeder["name"]
    assert api(board_a).delete("/api/platform/decoy-hits/").status_code == 403
    assert client.delete("/api/platform/decoy-hits/").json()["hits"] == []
    # gelöschter Köder: keine Auslösung mehr
    client.delete(f"{URL}{koeder['id']}/")
    api(board_a).get(f"/api/orgs/{orgs['a'].pk}/members/{koeder['id']}/")
    assert not hits()


def test_andere_nummern_im_pfad_zaehlen_nicht():
    treffer = decoys.MEMBER_ROUTE.search
    assert treffer("api/orgs/<int:org_id>/members/<int:pk>/")
    assert treffer("api/orgs/<int:org_id>/members/<int:member_pk>/fee-proofs/")
    assert not treffer("api/orgs/<int:org_id>/federation/members/<int:pk>/")
    assert not treffer("api/orgs/<int:org_id>/members/")


def test_zeitgesteuerte_aufgaben_lassen_den_koeder_in_ruhe(db, koeder, orgs, settings, monkeypatch):
    """Keine Aufgabe des Zeitplans schreibt dem Köder oder fasst ihn an (Glückwünsche,
    Erinnerungen, Jubiläen …): Sie arbeiten je Verein, und der Köder gehört keinem."""
    import importlib
    import socket

    def kein_netz(*args, **kwargs):
        raise OSError("Tests gehen nicht ins Netz")

    monkeypatch.setattr(socket.socket, "connect", kein_netz)
    monkeypatch.setattr(socket, "getaddrinfo", kein_netz)
    settings.EMAIL_BACKEND = "outbox.backend.OutboxBackend"
    make_member(orgs["a"], "Erika", "Musterfrau")
    gelaufen = 0
    for eintrag in settings.CELERY_BEAT_SCHEDULE.values():
        modul, name = eintrag["task"].rsplit(".", 1)
        aufgabe = getattr(importlib.import_module(modul), name)
        try:
            aufgabe(*eintrag.get("args", ()), **eintrag.get("kwargs", {}))
        except Exception:  # noqa: BLE001, S112 - Aufgaben mit fremden Diensten (IMAP, Bank …)
            continue
        gelaufen += 1
    assert gelaufen >= len(settings.CELERY_BEAT_SCHEDULE) * 3 // 4
    assert not hits()
