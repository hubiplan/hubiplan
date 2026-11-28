"""Füllt den Demoverein so, dass die Antworten des Bereichs Termine jedes Feld zeigen.

Alles geht über die Schnittstelle, wie es die Web-Oberfläche täte: Rückmeldung mit Frist und
Plätzen, verschobener Termin, Terminreihe mit Ausnahme, Anhang, Veranstaltungsfinanzen,
Dienstplan, Belegung, Rundschreiben, Veranstaltungsseite, öffentlicher Kalender und ein fremder
Kalender (dessen Abholen hier eine feste Antwort bekommt, ohne Netz).
"""

from __future__ import annotations

import datetime
from unittest import mock

from django.test import Client
from django.utils import timezone

from .feldabgleich_mitglieder import _foto

JSON = "application/json"

ICAL = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Beispiel//Kalender//DE
BEGIN:VEVENT
UID:bezirk-1@example.org
DTSTART:{start}
DTEND:{ende}
SUMMARY:Bezirksversammlung
LOCATION:Musterhalle
END:VEVENT
BEGIN:VEVENT
UID:bezirk-2@example.org
DTSTART:{start2}
DTEND:{ende2}
SUMMARY:Bezirksjugendtag
END:VEVENT
END:VCALENDAR
"""


def fuelle(client: Client, club, von: str, bis: str) -> None:
    basis = f"/api/orgs/{club.pk}/"

    def sende(methode: str, pfad: str, daten=None, erwartet=(200, 201), **mehr):
        art = (
            {} if mehr.get("format") == "multipart" or methode == "get" else {"content_type": JSON}
        )
        antwort = getattr(client, methode)(basis + pfad, daten, **art)
        assert antwort.status_code in erwartet, (pfad, antwort.status_code, antwort.content[:300])
        return antwort.json() if antwort.content else None

    liste = sende("get", f"events/?from={von}&to={bis}")
    jetzt = timezone.now()
    kommend = [o for o in liste["items"] if o["own"] and o["starts_at"] > jetzt.isoformat()]
    einzeln = next(o for o in kommend if not o["is_series"] and o["visibility"] == "public")
    reihe = next(o for o in kommend if o["is_series"])
    a = einzeln["event_id"]
    start = datetime.datetime.fromisoformat(einzeln["starts_at"])

    # Rückmeldung mit Frist und Plätzen, Koordinaten, Erinnerung, eigene Weitergabe; die
    # neue Zeit gilt als „verschoben“ (changed_at)
    sende(
        "patch",
        f"events/{a}/",
        {
            "starts_at": (start + datetime.timedelta(hours=1)).isoformat(),
            "ends_at": (start + datetime.timedelta(hours=4)).isoformat(),
            "latitude": 51.2,
            "longitude": 6.7,
            "rsvp_enabled": True,
            "rsvp_deadline": (start - datetime.timedelta(days=2)).isoformat(),
            "rsvp_capacity": 40,
            "rsvp_guests": True,
            "rsvp_maybe": True,
            "rsvp_note": True,
            "rsvp_note_question": "Was bringst du mit?",
            "remind_days": 3,
            "share_up": True,
            "share_down": False,
        },
    )
    # Rückmeldung, vom Vorstand für ein Mitglied eingetragen
    offen = sende("get", f"events/{a}/responses/")["open"]
    sende(
        "put",
        f"events/{a}/responses/",
        {
            "membership_id": offen[0]["membership_id"],
            "status": "yes",
            "guests": 1,
            "note": "Kuchen",
        },
    )
    # Anhang
    sende("post", f"events/{a}/attachments/", {"file": _foto()}, format="multipart")
    # dazu ein Dokument aus der Ablage als Anhang
    dokumente = sende("get", f"events/{a}/attachments/")["documents"]
    sende("post", f"events/{a}/attachments/", {"document": dokumente[0]["id"]})
    # Veranstaltungsfinanzen, Dienstplan, Belegung, Rundschreiben, Veranstaltungsseite
    sende("post", f"events/{a}/project/", {"create": True})
    sende("post", "helpers/", {"title": "Thekendienst", "event": a})
    # Belegung: ein Gegenstand des Vereins bekommt dafür einen Buchungskalender
    from materials.models import MaterialItem

    gegenstand = MaterialItem.objects.filter(
        organization=club, department=None, deleted_at__isnull=True
    ).first()
    gegenstand.booking_rules = {"enabled": True, "approval": False}
    gegenstand.save(update_fields=["booking_rules"])
    sende(
        "post",
        "bookings/",
        {
            "item": gegenstand.pk,
            "event": a,
            "starts_at": (start + datetime.timedelta(hours=1)).isoformat(),
            "ends_at": (start + datetime.timedelta(hours=4)).isoformat(),
        },
    )
    sende("post", f"circulars/from-event/{a}/", {})
    sende("post", "website/texts/event-page/", {"event": a})

    # Terminreihe mit Ende und einer verlegten Ausnahme
    r = reihe["event_id"]
    sende(
        "patch",
        f"events/{r}/",
        {"repeat_until": (jetzt.date() + datetime.timedelta(days=300)).isoformat()},
    )
    sende(
        "put",
        f"events/{r}/occurrence/",
        {"original_start": reihe["original_start"], "is_cancelled": True, "note": "Halle belegt"},
    )

    spaeter = next(
        o for o in kommend if o["event_id"] == r and o["original_start"] != reihe["original_start"]
    )
    neu = datetime.datetime.fromisoformat(spaeter["starts_at"]) + datetime.timedelta(days=1)
    sende(
        "put",
        f"events/{r}/occurrence/",
        {
            "original_start": spaeter["original_start"],
            "starts_at": neu.isoformat(),
            "ends_at": (neu + datetime.timedelta(hours=2)).isoformat(),
            "note": "einen Tag später",
        },
    )

    # Untereinheit ohne eigene Verwaltung: ihre Termine pflegt der Vorstand
    sende("post", "departments/", {"name": "Jugendgruppe"})

    # Kalender öffentlich: Links zum Abonnieren
    sende("put", "events/publication/", {"is_public": True, "renew": False})

    # Fremder Kalender (iCal); das Abholen bekommt eine feste Antwort
    tag = (jetzt + datetime.timedelta(days=20)).strftime("%Y%m%d")
    tag2 = (jetzt + datetime.timedelta(days=27)).strftime("%Y%m%d")
    text = ICAL.format(
        start=f"{tag}T180000Z",
        ende=f"{tag}T200000Z",
        start2=f"{tag2}T090000Z",
        ende2=f"{tag2}T160000Z",
    )
    kategorie = sende("get", "events/categories/")[0]["id"]
    with mock.patch("events.external._get", return_value=(200, text.encode())):
        sende(
            "post",
            "events/external/",
            {
                "name": "Bezirksverband",
                "kind": "ical",
                "token": "https://kalender.example.org/bezirk.ics",
                "secret": "",
                "category": kategorie,
                "visibility": "members",
                "share_down": False,
                "is_active": True,
            },
        )
    # einen der fremden Termine hier ausblenden
    fremd = next(
        o
        for o in sende("get", f"events/?from={von}&to={bis}")["items"]
        if o["title"] == "Bezirksjugendtag"
    )
    sende("post", f"events/{fremd['event_id']}/hide/", {}, erwartet=(200, 201, 204))
