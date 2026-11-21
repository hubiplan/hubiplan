"""Vorstandsaufgaben in der App: Beitrittsanträge entscheiden, Belegungsanfragen freigeben,
Versammlung leiten (Anwesenheit, Anmeldung per App, Abstimmungen). Alle Daten erfunden."""
# ruff: noqa: F811  (Fixtures als Parameter)

import datetime
import secrets
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from admission.models import Application
from bookings.models import Booking
from core.tenancy import tenant_context
from materials.models import MaterialItem
from meetings.models import Meeting

from .factories import give_role, make_member, make_user
from .test_app_devices import APP, app
from .test_app_verwaltung import admin_token, board  # noqa: F401
from .test_m12_events import JSON, cal  # noqa: F401

pytestmark = pytest.mark.django_db
ADMIN = f"{APP}admin/u/"
BERLIN = ZoneInfo("Europe/Berlin")


def at(days, hour):
    day = timezone.localdate() + datetime.timedelta(days=days)
    return datetime.datetime.combine(day, datetime.time(hour), BERLIN).isoformat()


def modules(club, *names):
    club.enabled_modules = sorted({*club.enabled_modules, *names})
    club.save()


def test_vorstandsrechte_zeigen_die_verwaltung(cal, api):
    from devices.admin_api import admin_units

    club = cal["a"]
    modules(club, "meetings", "bookings", "infrastructure")
    user = make_user("leitung@example.org")
    give_role(user, club, ["meetings.view", "meetings.edit"], name="Versammlungsleitung")
    unit = next(u for u in admin_units(user) if u["id"] == club.pk)
    assert "meetings.edit" in unit["permissions"] and "meetings" in unit["modules"]
    other = make_user("belegung@example.org")
    give_role(other, club, ["bookings.view", "bookings.edit"], name="Hauswart")
    assert any(u["id"] == club.pk for u in admin_units(other))


def test_beitrittsantrag_in_der_app(board, admin_token, cal):
    club = cal["a"]
    with tenant_context(club.pk):
        antrag = Application.objects.create(
            organization=club,
            status="open",
            data={"first_name": "Erika", "last_name": "Muster", "email": "erika@example.org"},
            token_hash=secrets.token_hex(32),
        )
    c = app(admin_token)
    base = f"{ADMIN}{club.pk}/admission/"
    listing = c.get(base).json()
    row = next(r for r in listing["results"] if r["id"] == antrag.pk)
    assert row["name"] == "Muster, Erika" or "Erika" in row["name"]
    assert listing["counts"]["open"] >= 1
    detail = c.get(f"{base}{antrag.pk}/").json()
    assert detail["may_decide"] is True and detail["status"] == "open"
    # Korrigieren bleibt im Browser
    assert c.patch(f"{base}{antrag.pk}/", {"city": "X"}, content_type=JSON).status_code == 405
    done = c.post(
        f"{base}{antrag.pk}/reject/", {"note": "Doppelt gestellt"}, content_type=JSON
    ).json()
    assert done["status"] == "rejected" and done["decision_note"] == "Doppelt gestellt"
    tasks = c.get(f"{ADMIN}{club.pk}/tasks/").json()["items"]
    assert not any(t["kind"] == "application" and t["ref"] == antrag.pk for t in tasks)


def test_beitrittsantrag_als_offene_aufgabe(board, admin_token, cal):
    club = cal["a"]
    with tenant_context(club.pk):
        from admission import services

        services.form_for(club)
        antrag = Application.objects.create(
            organization=club,
            status="open",
            data={"first_name": "Otto", "last_name": "Probe", "email": "otto@example.org"},
            token_hash=secrets.token_hex(32),
        )
    tasks = app(admin_token).get(f"{ADMIN}{club.pk}/tasks/").json()["items"]
    assert any(t["kind"] == "application" and t["ref"] == antrag.pk for t in tasks)


def test_belegungsanfrage_freigeben(board, admin_token, cal, api):
    club = cal["a"]
    modules(club, "bookings", "infrastructure")
    give_role(board["user"], club, ["bookings.view", "bookings.edit"], name="Hauswart")
    hall = MaterialItem.objects.create(
        organization=club,
        kind="facility",
        title="Saal",
        description="x",
        location_kind="address",
        address={
            "street": "Musterweg 1",
            "postal_code": "12345",
            "city": "Musterstadt",
            "country": "DE",
        },
        facility_type="building",
        booking_rules={"enabled": True, "approval": True},
    )
    member = make_user("schuetze@example.org")
    give_role(member, club, ["bookings.view"], name="Schütze")
    resp = api(member).post(
        f"/api/orgs/{club.pk}/bookings/",
        {"item": hall.pk, "title": "Geburtstag", "starts_at": at(5, 18), "ends_at": at(5, 23)},
        content_type=JSON,
    )
    assert resp.status_code == 201, resp.json()
    booking = resp.json()
    assert booking["status"] == "requested"
    c = app(admin_token)
    base = f"{ADMIN}{club.pk}/bookings/"
    listing = c.get(base, {"start": timezone.localdate().isoformat()}).json()
    assert [r["id"] for r in listing["requests"]] == [booking["id"]]
    tasks = c.get(f"{ADMIN}{club.pk}/tasks/").json()["items"]
    assert any(t["kind"] == "booking" and t["ref"] == booking["id"] for t in tasks)
    # Neue Buchungen bleiben im Browser
    assert c.post(base, {"item": hall.pk}, content_type=JSON).status_code == 405
    # Veralteter Stand wird abgelehnt
    stale = c.post(
        f"{base}{booking['id']}/decision/",
        {"action": "confirm", "version": booking["version"] + 1},
        content_type=JSON,
    )
    assert stale.status_code == 409
    done = c.post(
        f"{base}{booking['id']}/decision/",
        {"action": "confirm", "version": booking["version"]},
        content_type=JSON,
    ).json()
    assert done["status"] == "confirmed"
    assert Booking.objects.get(pk=booking["id"]).status == "confirmed"


def test_versammlung_leiten(board, admin_token, cal, api):
    club = cal["a"]
    modules(club, "meetings")
    give_role(board["user"], club, ["meetings.view", "meetings.edit"], name="Versammlungsleitung")
    browser = api(board["user"])
    url = f"/api/orgs/{club.pk}/meetings/"
    kind = next(
        k for k in browser.get(url + "kinds/").json() if k["name"] == "Jahreshauptversammlung"
    )
    browser.patch(f"{url}kinds/{kind['id']}/", {"online_voting": True}, content_type=JSON)
    meeting = browser.post(
        url, {"kind": kind["id"], "starts_at": at(1, 19), "ends_at": at(1, 22)}, content_type=JSON
    ).json()
    Meeting.objects.filter(pk=meeting["id"]).update(status="invited")
    item = next(a for a in meeting["agenda"] if a["type"] == "resolution")

    c = app(admin_token)
    base = f"{ADMIN}{club.pk}/meetings/"
    listing = c.get(base).json()
    assert listing[0]["id"] == meeting["id"] and listing[0]["can_attendance"] is True
    assert c.get(f"{base}{meeting['id']}/").json()["agenda"]
    # Vorbereiten bleibt im Browser
    assert c.patch(f"{base}{meeting['id']}/", {}, content_type=JSON).status_code == 405

    # Einlass: Mitglied (z. B. nach dem Ausweis-Scan) und Gast eintragen, Gast wieder entfernen
    anna = make_member(club, "Anna", "Beispiel")
    att = f"{base}{meeting['id']}/attendance/"
    data = c.post(att, {"membership": anna.pk, "status": "present"}, content_type=JSON).json()
    assert any(r["membership"] == anna.pk and r["status"] == "present" for r in data["rows"])
    data = c.post(att, {"name": "Gast Probe", "status": "present"}, content_type=JSON).json()
    guest = next(r for r in data["rows"] if r["name"] == "Gast Probe")
    data = c.delete(f"{att}{guest['id']}/").json()
    assert not any(r["name"] == "Gast Probe" for r in data["rows"])

    # Anmeldung per App öffnen: Code für den QR-Code
    live = f"{base}{meeting['id']}/live/"
    data = c.post(live, {"open": True}, content_type=JSON).json()
    assert data["checkin_open"] is True and data["code"] and data["refresh_in"] >= 1

    # Abstimmung anlegen, starten, beenden
    polls = f"{base}{meeting['id']}/polls/"
    resp = c.post(polls, {"agenda_item": item["id"], "question": "Entlastung?"}, content_type=JSON)
    assert resp.status_code == 201, resp.json()
    poll = resp.json()["polls"][0]
    assert poll["status"] == "draft"
    data = c.post(f"{polls}{poll['id']}/", {"action": "open"}, content_type=JSON).json()
    assert data["polls"][0]["status"] == "open"
    data = c.post(f"{polls}{poll['id']}/", {"action": "close"}, content_type=JSON).json()
    assert data["polls"][0]["status"] == "closed" and data["polls"][0]["result"] is not None


def test_ohne_versammlungsrecht_kein_zugriff(board, admin_token, cal):
    club = cal["a"]
    modules(club, "meetings")
    c = app(admin_token)
    assert c.get(f"{ADMIN}{club.pk}/meetings/").status_code == 403
