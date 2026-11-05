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


def test_ausleihe_mit_ausgabe_und_rueckgabe(setup):
    s = setup
    beamer = MaterialItem.objects.create(
        organization=s["org"],
        title="Beamer",
        description="Vereinsbeamer",
        location_kind="unknown",
        booking_rules={"enabled": True},
    )
    response = book(s["member"], s["url"], beamer, at(4, 9), at(5, 18), title="Vortrag")
    assert response.status_code == 201, response.content
    booking = response.json()
    assert booking["status"] == "confirmed"
    assert booking["loan"] is True
    url = f"{s['url']}{booking['id']}/handover/"
    # Ausgeben darf nur die Verwaltung
    assert (
        s["member"]
        .post(url, {"action": "out", "version": booking["version"]}, content_type=JSON)
        .status_code
        == 403
    )
    out = s["admin"].post(url, {"action": "out", "version": booking["version"]}, content_type=JSON)
    assert out.status_code == 200, out.content
    assert out.json()["handed_out_at"]
    back = s["admin"].post(
        url,
        {
            "action": "return",
            "version": out.json()["version"],
            "update_item": True,
            "condition": "limited",
            "condition_note": "Lampe flackert",
        },
        content_type=JSON,
    )
    assert back.status_code == 200, back.content
    assert back.json()["returned_at"]
    beamer.refresh_from_db()
    assert beamer.condition == "limited"
    assert beamer.condition_note == "Lampe flackert"
    assert beamer.revisions.count() == 1
    # Ohne Häkchen bleibt der Zustand unberührt
    undo = s["admin"].post(
        url, {"action": "undo", "version": back.json()["version"]}, content_type=JSON
    )
    assert undo.json()["returned_at"] is None
    again = s["admin"].post(
        url,
        {"action": "return", "version": undo.json()["version"], "condition": "ready"},
        content_type=JSON,
    )
    assert again.status_code == 200
    beamer.refresh_from_db()
    assert beamer.condition == "limited"


def test_bedarf_eines_einzeltermins_wird_buchung(setup):
    s = setup
    from events.models import Event

    begin = (timezone.now() + datetime.timedelta(days=3)).replace(microsecond=0)
    series = Event.objects.create(
        organization=s["org"],
        title="Übungsabend",
        starts_at=begin,
        ends_at=begin + datetime.timedelta(hours=2),
        repeat="weekly",
    )
    second = begin + datetime.timedelta(days=7)
    response = s["admin"].post(
        s["url"],
        {"item": s["hall"].pk, "event": series.pk, "occurrence": second.isoformat()},
        content_type=JSON,
    )
    assert response.status_code == 201, response.content
    booking = Booking.objects.get(pk=response.json()["id"])
    assert booking.title == "Übungsabend"
    assert booking.event_id is None
    assert booking.repeat == "none"
    assert booking.starts_at == second
    assert booking.ends_at == second + datetime.timedelta(hours=2)
    wrong = s["admin"].post(
        s["url"],
        {
            "item": s["stand"].pk,
            "event": series.pk,
            "occurrence": (second + datetime.timedelta(hours=1)).isoformat(),
        },
        content_type=JSON,
    )
    assert wrong.status_code == 400


def test_anfrage_im_portal_und_benachrichtigung(
    setup, api, mailoutbox, django_capture_on_commit_callbacks
):
    from portal.models import PortalAccess

    from .factories import make_member

    s = setup
    org = s["org"]
    org.member_portal_enabled = True
    org.save(update_fields=["member_portal_enabled"])
    s["hall"].booking_rules = {"enabled": True, "approval": True, "portal": True}
    s["hall"].save()
    membership = make_member(org, "Erika", "Beispiel", email="erika@example.org")
    user = make_user("erika@example.org")
    access = PortalAccess.objects.create(organization=org, membership=membership, user=user)
    portal = api(user)
    url = f"/api/portal/{access.pk}/bookings/"
    data = portal.get(url).json()
    # Nur Objekte mit „im Portal anfragen“
    assert [i["title"] for i in data["items"]] == ["Saal"]
    assert book(s["admin"], s["url"], s["hall"], at(6, 10), at(6, 12)).status_code == 201
    busy = portal.get(url + f"?start={timezone.localdate() + datetime.timedelta(days=6)}").json()
    assert {r["title"] for r in busy["occurrences"]} == {"Belegt"}
    response = portal.post(
        url,
        {"item": s["hall"].pk, "title": "Geburtstag", "starts_at": at(7, 15), "ends_at": at(7, 20)},
        content_type=JSON,
    )
    assert response.status_code == 201, response.content
    request = response.json()
    assert request["status"] == "requested"
    # Fremde Objekte lassen sich nicht anfragen
    assert (
        portal.post(
            url,
            {"item": s["stand"].pk, "title": "x", "starts_at": at(7, 15), "ends_at": at(7, 20)},
            content_type=JSON,
        ).status_code
        == 400
    )
    booking = s["admin"].get(f"{s['url']}{request['id']}/").json()
    with django_capture_on_commit_callbacks(execute=True):
        confirm = s["admin"].post(
            f"{s['url']}{request['id']}/decision/",
            {"action": "confirm", "version": booking["version"]},
            content_type=JSON,
        )
    assert confirm.status_code == 200, confirm.content
    assert [m.to for m in mailoutbox] == [["erika@example.org"]]
    assert "Geburtstag" in mailoutbox[0].subject
    own = portal.get(url).json()["own"]
    assert own[0]["status"] == "confirmed"
    cancel = portal.post(
        f"{url}{request['id']}/cancel/", {"version": own[0]["version"]}, content_type=JSON
    )
    assert cancel.json()["status"] == "cancelled"
    # Ein anderes Mitglied sieht den Portalzugang nicht
    other = make_user("fremd@example.org")
    assert api(other).get(url).status_code == 404
