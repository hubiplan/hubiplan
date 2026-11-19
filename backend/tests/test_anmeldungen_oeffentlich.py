# ruff: noqa: F811  (Fixtures aus test_m9_billing und test_anmeldungen)
"""Öffentliche Anmeldung für Nichtmitglieder (konzepte/veranstaltungen-anmeldung-gebuehr.md,
Stufe A4): Formular mit Spamschutz, Bestätigungslink, erst danach Platz und Rechnung, Link
„Anmeldung ansehen“ zum Abmelden. Alle Daten erfunden."""

import datetime

import pytest
from django.core import mail
from django.test import Client
from django.utils import timezone

from core.tenancy import rls_bypass
from registrations.models import PendingRegistration, Registration
from registrations.public import purge_pending
from website import contact

from .test_anmeldungen import JSON, einrichten, fest, ok, soon  # noqa: F401
from .test_m9_billing import base, c, club, setup, zug  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def leichte_aufgabe(monkeypatch):
    monkeypatch.setattr(contact, "MIN_SECONDS", 0)
    monkeypatch.setattr(contact, "DIFFICULTY", 4)


def _public(c, fest):
    """Termin öffentlich machen und die öffentliche Anmeldung einschalten."""
    ok(
        c.patch(
            f"{fest['org']}/events/{fest['event']['id']}/",
            {"visibility": "public"},
            content_type=JSON,
        )
    )
    return einrichten(c, fest, public=True)


def _token(message, marker: str) -> str:
    for word in message.body.split():
        if marker in word:
            return word.rstrip("/").rsplit("/", 1)[-1]
    raise AssertionError(message.body)


def _send(key: str, **extra):
    form = ok(Client().get(f"/api/public/registration/{key}/"))
    ch = form["challenge"]
    guest = next(p for p in form["offer"]["prices"] if p["name"] == "Gäste")
    body = {
        "name": "Erika Beispiel",
        "email": "erika@example.org",
        "phone": "0123 456789",
        "persons": [
            {"name": "Erika Beispiel", "price_id": guest["id"]},
            {"name": "Max Beispiel", "price_id": guest["id"]},
        ],
        "privacy_accepted": True,
        "challenge": ch["token"],
        "nonce": contact.solve(ch["salt"], ch["difficulty"]),
        **extra,
    }
    return Client().post(f"/api/public/registration/{key}/", body, JSON)


def test_nur_bei_oeffentlichen_terminen(c, fest):
    resp = c.put(
        fest["url"],
        {
            "closes_at": soon(30),
            "prices": [{"name": "Alle", "steps": [{"amount": "0"}]}],
            "public": True,
        },
        content_type=JSON,
    )
    assert resp.status_code == 400 and "öffentlich" in resp.content.decode()
    data = _public(c, fest)
    url = data["offer"]["public_url"]
    assert url and "/anmeldung/" in url
    key = url.rsplit("/", 1)[-1]
    form = ok(Client().get(f"/api/public/registration/{key}/"))
    assert form["event"]["title"] == "Vereinsausflug"
    # Tarife nur für Mitglieder fehlen, Verwaltungsangaben auch
    assert all(p["applies"] != "members" for p in form["offer"]["prices"])
    assert "taken" not in form["offer"] and "category" not in form["offer"]
    assert form["privacy_text"] and form["challenge"]["salt"]
    # Termin nicht mehr öffentlich: Formular weg
    ok(
        c.patch(
            f"{fest['org']}/events/{fest['event']['id']}/",
            {"visibility": "members"},
            content_type=JSON,
        )
    )
    assert Client().get(f"/api/public/registration/{key}/").status_code == 404


def test_anmelden_bestaetigen_ansehen_abmelden(c, fest, django_capture_on_commit_callbacks):
    data = _public(c, fest)
    key = data["offer"]["public_url"].rsplit("/", 1)[-1]
    # Ohne Datenschutzhinweis nicht
    resp = _send(key, privacy_accepted=False)
    assert resp.status_code == 400 and "Datenschutz" in resp.content.decode()
    # Honigtopf: still verworfen
    assert _send(key, homepage="https://spam.example.org").status_code == 201
    with rls_bypass():
        assert not PendingRegistration.objects.exists()
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        ok(_send(key), 201)
    with rls_bypass():
        assert PendingRegistration.objects.count() == 1
        assert not Registration.objects.filter(source="public").exists()
    confirm = [m for m in mail.outbox if "Anmeldung bestätigen" in m.subject]
    assert confirm and confirm[0].to == ["erika@example.org"]
    token = _token(confirm[0], "/anmeldung/bestaetigen/")
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        done = ok(Client().post(f"/api/public/registration/confirm/{token}/"))
    reg = done["registration"]
    assert reg["status"] == "registered" and reg["total"] == "80.00"
    assert reg["invoice"] is not None and done["token"]
    with rls_bypass():
        row = Registration.objects.get(pk=reg["id"])
        assert row.source == "public" and row.access_nonce
        assert not PendingRegistration.objects.exists()
    sent = [m for m in mail.outbox if "Anmeldebestätigung" in m.subject]
    assert sent and "/meine-anmeldung/" in sent[0].body
    # Link nur einmal
    assert Client().post(f"/api/public/registration/confirm/{token}/").status_code == 404
    link = _token(sent[0], "/meine-anmeldung/")
    mine = ok(Client().get(f"/api/public/registration/mine/{link}/"))
    assert mine["registration"]["number"] == reg["number"]
    assert mine["registration"]["can_cancel"] is True
    assert Client().get("/api/public/registration/mine/falsch/").status_code == 404
    # Eine Person abmelden, dann den Rest
    first = mine["registration"]["participants"][0]["id"]
    quote = ok(Client().get(f"/api/public/registration/mine/{link}/cancel/?participants={first}"))
    assert "fee" in quote
    with django_capture_on_commit_callbacks(execute=True):
        part = ok(
            Client().post(
                f"/api/public/registration/mine/{link}/cancel/", {"participants": [first]}, JSON
            )
        )
    states = [p["status"] for p in part["registration"]["participants"]]
    assert states == ["cancelled", "active"]
    with django_capture_on_commit_callbacks(execute=True):
        gone = ok(Client().post(f"/api/public/registration/mine/{link}/cancel/", {}, JSON))
    assert gone["registration"]["status"] == "cancelled"


def test_unbestaetigte_anmeldung_verfaellt(c, fest, django_capture_on_commit_callbacks):
    data = _public(c, fest)
    key = data["offer"]["public_url"].rsplit("/", 1)[-1]
    with django_capture_on_commit_callbacks(execute=True):
        ok(_send(key), 201)
    token = _token(
        [m for m in mail.outbox if "Anmeldung bestätigen" in m.subject][-1],
        "/anmeldung/bestaetigen/",
    )
    assert purge_pending(timezone.now() + datetime.timedelta(hours=25)) == 1
    assert Client().post(f"/api/public/registration/confirm/{token}/").status_code == 404


def test_webseite_zeigt_anmeldung_am_termin(c, fest, club):
    from .factories import make_website

    club.enabled_modules = sorted({*club.enabled_modules, "website"})
    club.save()
    make_website(club, public_key="anmeldung-site", state="public")
    data = _public(c, fest)
    items = ok(Client().get("/api/public/site/v1/anmeldung-site/events/"))["events"]
    item = next(i for i in items if i["title"] == "Vereinsausflug")
    reg = item["registration"]
    assert reg["url"] == data["offer"]["public_url"] and reg["can_join"] is True
    assert reg["free"] == 5 and reg["state"] == "open"
    # Nur Tarife für Nichtmitglieder, mit aktuellem Preis; keine Teilnehmenden
    assert {p["name"] for p in reg["prices"]} == {"Erwachsene", "Kinder bis 14", "Gäste"}
    assert "participants" not in reg and "taken" not in reg
    # Ohne öffentliche Anmeldung: nichts
    einrichten(c, fest, public=False)
    items = ok(Client().get("/api/public/site/v1/anmeldung-site/events/"))["events"]
    assert next(i for i in items if i["title"] == "Vereinsausflug")["registration"] is None


def test_veranstaltungsseite(c, fest, club):
    """Konzept 3.8a: Textseite zum Termin mit Eckdaten, Preisen und Anmeldeknopf; Menüpunkt
    bis zum Ende, danach wahlweise ausgeblendet."""
    from website import event_page
    from website.content_models import WebsiteText

    from .factories import make_website

    club.enabled_modules = sorted({*club.enabled_modules, "website"})
    club.save()
    make_website(club, public_key="fest-site", state="public")
    org = fest["org"]
    event_id = fest["event"]["id"]
    # Nur bei öffentlichen Terminen
    resp = c.post(f"{org}/website/texts/event-page/", {"event": event_id}, content_type=JSON)
    assert resp.status_code == 400 and "öffentlich" in resp.content.decode()
    data = _public(c, fest)
    page = ok(
        c.post(f"{org}/website/texts/event-page/", {"event": event_id}, content_type=JSON), 201
    )
    assert page["kind"] == "page" and page["slug"] == "vereinsausflug"
    assert page["event"]["id"] == event_id and not page["is_published"]
    detail = ok(c.get(f"{org}/events/{event_id}/"))
    assert detail["web_page"]["id"] == page["id"] and detail["web_page"]["is_published"] is False
    # Zweimal: dieselbe Seite
    again = ok(c.post(f"{org}/website/texts/event-page/", {"event": event_id}, content_type=JSON))
    assert again["id"] == page["id"]
    # Entwurf: noch nicht öffentlich
    public = "/api/public/site/v1/fest-site"
    assert Client().get(f"{public}/pages/vereinsausflug/").status_code == 404
    ok(c.post(f"{org}/website/texts/{page['id']}/publish/"))
    shown = ok(Client().get(f"{public}/pages/vereinsausflug/"))
    ev = shown["event"]
    assert ev["title"] == "Vereinsausflug" and ev["ended"] is False
    reg = ev["registration"]
    assert reg["url"] == data["offer"]["public_url"] and reg["can_join"] is True
    assert "cancel_text" in reg and "terms" in reg and "participants" not in reg
    nav = ok(Client().get(f"{public}/"))["nav"]
    entry = next(n for n in nav if n.get("slug") == "vereinsausflug")
    assert entry["event"] is True
    items = ok(Client().get(f"{public}/events/"))["events"]
    assert next(i for i in items if i["title"] == "Vereinsausflug")["page"] == "vereinsausflug"
    # Nach dem Ende: kein Menüpunkt, Seite bleibt als Rückblick oder wird ausgeblendet
    with rls_bypass():
        text = WebsiteText.objects.select_related("event").get(pk=page["id"])
    after = event_page.last_day(text.event) + datetime.timedelta(days=1)
    assert event_page.in_menu(text, after - datetime.timedelta(days=1))
    assert not event_page.in_menu(text, after) and not event_page.hidden(text, after)
    ok(
        c.put(
            f"{org}/website/texts/{page['id']}/",
            {"hide_after_event": True},
            content_type=JSON,
        )
    )
    with rls_bypass():
        text.refresh_from_db()
    assert event_page.hidden(text, after) and not event_page.hidden(
        text, after - datetime.timedelta(days=1)
    )
    # Termin nicht mehr öffentlich: Seite ohne Eckdaten, Termin ohne Verweis
    ok(c.patch(f"{org}/events/{event_id}/", {"visibility": "members"}, content_type=JSON))
    assert ok(Client().get(f"{public}/pages/vereinsausflug/"))["event"] is None
