"""Buchungskalender für Infrastruktur und Material."""

import datetime
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from bookings.models import Booking, BookingSlot
from materials.models import MaterialItem

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"
BERLIN = ZoneInfo("Europe/Berlin")
ADDRESS = {"street": "Musterweg 1", "postal_code": "12345", "city": "Musterstadt", "country": "DE"}


def at(days, hour):
    day = timezone.localdate() + datetime.timedelta(days=days)
    return datetime.datetime.combine(day, datetime.time(hour), BERLIN).isoformat()


@pytest.fixture
def setup(orgs, api):
    org = orgs["a"]
    org.enabled_modules = sorted(
        set(org.enabled_modules) | {"material", "infrastructure", "events"}
    )
    org.save()
    admin = make_user("verwalter@example.org")
    give_role(admin, org, permissions=["infrastructure.edit", "material.edit", "events.edit"])
    member = make_user("schuetze@example.org")
    give_role(member, org, permissions=["bookings.view"], name="Schütze")
    rules = {"enabled": True, "approval": True, "buffer_after": 30}
    house = MaterialItem.objects.create(
        organization=org,
        kind="facility",
        title="Schützenhaus",
        description="Vereinsheim",
        location_kind="address",
        address=ADDRESS,
        facility_type="building",
        booking_rules=rules,
    )
    hall, stand = (
        MaterialItem.objects.create(
            organization=org,
            kind="facility",
            title=title,
            description="x",
            location_kind="facility",
            facility=house,
            facility_type="room",
            booking_rules=rules,
        )
        for title in ("Saal", "Stand")
    )
    return {
        "org": org,
        "admin": api(admin),
        "member": api(member),
        "url": f"/api/orgs/{org.pk}/bookings/",
        "house": house,
        "hall": hall,
        "stand": stand,
    }


def book(client, url, item, start, end, **kwargs):
    return client.post(
        url,
        {"item": item.pk, "title": "Training", "starts_at": start, "ends_at": end, **kwargs},
        content_type=JSON,
    )


def test_konflikte_mit_ruestzeit_und_bereichen(setup):
    s = setup
    first = book(s["admin"], s["url"], s["hall"], at(2, 18), at(2, 20))
    assert first.status_code == 201, first.content
    assert first.json()["status"] == "confirmed"
    # Rüstzeit 30 Minuten nach dem Ende: 20:15 ist noch belegt
    clash = book(s["admin"], s["url"], s["hall"], at(2, 20).replace(":00:00", ":15:00"), at(2, 22))
    assert clash.status_code == 409
    assert clash.json()["conflicts"]
    # Anderer Bereich zur selben Zeit: frei
    assert book(s["admin"], s["url"], s["stand"], at(2, 18), at(2, 20)).status_code == 201
    # Das ganze Haus belegt alle Bereiche: Konflikt
    assert book(s["admin"], s["url"], s["house"], at(2, 19), at(2, 21)).status_code == 409
    assert book(s["admin"], s["url"], s["house"], at(3, 19), at(3, 21)).status_code == 201
    assert book(s["admin"], s["url"], s["stand"], at(3, 20), at(3, 22)).status_code == 409


def test_anfrage_freigabe_und_sichtbarkeit(setup):
    s = setup
    response = book(s["member"], s["url"], s["hall"], at(5, 10), at(5, 12), visibility="board")
    assert response.status_code == 201, response.content
    booking = response.json()
    assert booking["status"] == "requested"
    # Eine Anfrage blockiert noch nichts
    assert book(s["admin"], s["url"], s["hall"], at(5, 11), at(5, 13)).status_code == 201
    listing = s["admin"].get(s["url"] + f"?start={timezone.localdate()}").json()
    assert [r["id"] for r in listing["requests"]] == [booking["id"]]
    decide = s["admin"].post(
        f"{s['url']}{booking['id']}/decision/",
        {"action": "confirm", "version": booking["version"]},
        content_type=JSON,
    )
    assert decide.status_code == 409  # jetzt überschneidet sie sich
    # Die Mitglieder sehen die Buchung „nur Verwalter“ nicht im Detail
    other = make_user("andere@example.org")
    give_role(other, s["org"], permissions=["bookings.view"], name="Schütze")
    from django.test import Client

    client = Client()
    client.force_login(other)
    rows = client.get(s["url"] + f"?start={timezone.localdate()}").json()["occurrences"]
    titles = {r["title"] for r in rows}
    assert "Belegt" in titles
    # Das Mitglied darf nicht freigeben, aber seine Anfrage stornieren
    assert (
        s["member"]
        .post(
            f"{s['url']}{booking['id']}/decision/",
            {"action": "confirm", "version": booking["version"]},
            content_type=JSON,
        )
        .status_code
        == 403
    )
    cancel = s["member"].post(
        f"{s['url']}{booking['id']}/decision/",
        {"action": "cancel", "version": booking["version"]},
        content_type=JSON,
    )
    assert cancel.status_code == 200
    assert not BookingSlot.objects.filter(booking_id=booking["id"]).exists()


def test_serie_mit_ausfall(setup):
    s = setup
    response = book(
        s["admin"],
        s["url"],
        s["stand"],
        at(1, 19),
        at(1, 21),
        repeat="weekly",
        repeat_until=str(timezone.localdate() + datetime.timedelta(days=30)),
    )
    assert response.status_code == 201, response.content
    booking = response.json()
    slots = BookingSlot.objects.filter(booking_id=booking["id"], resource=s["stand"])
    assert slots.count() in (4, 5)
    second = slots.order_by("starts_at")[1]
    response = s["admin"].post(
        f"{s['url']}{booking['id']}/skip/",
        {"original_start": second.original_start.isoformat(), "version": booking["version"]},
        content_type=JSON,
    )
    assert response.status_code == 200, response.content
    assert not BookingSlot.objects.filter(
        booking_id=booking["id"], original_start=second.original_start
    ).exists()
    # Am ausgefallenen Abend ist der Stand frei
    start = timezone.localtime(second.starts_at, BERLIN)
    assert (
        book(
            s["admin"],
            s["url"],
            s["stand"],
            start.isoformat(),
            (start + datetime.timedelta(hours=1)).isoformat(),
        ).status_code
        == 201
    )


def test_buchung_folgt_dem_termin(setup):
    s = setup
    from events.models import Event

    begin = timezone.now() + datetime.timedelta(days=10)
    event = Event.objects.create(
        organization=s["org"],
        title="Jahreshauptversammlung",
        starts_at=begin,
        ends_at=begin + datetime.timedelta(hours=3),
    )
    response = s["admin"].post(
        s["url"], {"item": s["hall"].pk, "event": event.pk}, content_type=JSON
    )
    assert response.status_code == 201, response.content
    booking = Booking.objects.get(pk=response.json()["id"])
    assert booking.title == "Jahreshauptversammlung"
    event.starts_at = begin + datetime.timedelta(days=1)
    event.ends_at = event.starts_at + datetime.timedelta(hours=3)
    event.save()
    booking.refresh_from_db()
    assert booking.starts_at == event.starts_at
    assert BookingSlot.objects.get(booking=booking, resource=s["hall"]).starts_at == event.starts_at
    event.is_cancelled = True
    event.save()
    booking.refresh_from_db()
    assert booking.status == "cancelled"
    assert not booking.slots.exists()


def test_ohne_recht_und_ohne_kalender(setup, orgs, api):
    s = setup
    nobody = make_user("niemand@example.org")
    give_role(nobody, s["org"], permissions=["members.view"], name="Leser")
    assert api(nobody).get(s["url"]).status_code == 403
    s["stand"].booking_rules = {}
    s["stand"].save()
    assert book(s["admin"], s["url"], s["stand"], at(1, 10), at(1, 11)).status_code == 400
    # Defekte Objekte sind nicht buchbar, auch nicht für Mitglieder
    s["hall"].condition = "defective"
    s["hall"].save()
    assert book(s["member"], s["url"], s["hall"], at(1, 10), at(1, 11)).status_code == 403
