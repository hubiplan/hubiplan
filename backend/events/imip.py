"""Termineinladungen per Mail (iMIP, RFC 6047) lesen und schreiben.

Lesen (``read``): Eine Einladung aus Outlook, Thunderbird, Nextcloud, Apple- oder Google-
Kalender trägt einen Kalenderteil (``text/calendar`` oder eine ``.ics``-Datei) mit
``METHOD:REQUEST`` (neu oder geändert), ``METHOD:CANCEL`` (abgesagt) oder ``METHOD:REPLY``
(Antwort eines Teilnehmers). ``read`` liefert daraus genau einen Termin; Serien mit
Abweichungen (mehrere VEVENT mit ``RECURRENCE-ID``) nimmt HUBIplan nicht an.

Schreiben: ``reply`` (Antwort „angenommen“ an den Organisator einer Einladung an einen
Verteiler) und ``invitation`` (Kalenderteil in HUBIplans eigenen Einladungen, damit
Mailprogramme „Annehmen/Ablehnen“ zeigen, W1b). Die Antworten darauf gehen an eine
Antwortadresse ``termin+<code>@<Verteiler-Domain>`` (``reply_address``); der Code ist mit
dem Geheimnis des Servers unterschrieben und gilt nur für diesen Termin und dieses Mitglied.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import re
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import parseaddr

from django.conf import settings
from django.utils import timezone

from . import external
from .ical import _escape, _fold, _utc

# Ein Kalenderteil größer als das ist keine Einladung (Schutz vor Riesendateien)
MAX_ICS = 512 * 1024
METHODS = ("REQUEST", "CANCEL", "REPLY", "PUBLISH")
# Lokaler Teil der Antwortadresse (vor dem +); kein Verteiler darf so heißen
REPLY_LOCAL = "termin"

# Konferenzlinks, die als Videolink des Termins übernommen werden
VIDEO_LINK = re.compile(
    r"https://[^\s<>\"'\\]*?(?:/call/[A-Za-z0-9]+|/meet/[^\s<>\"'\\]+|teams\.microsoft\.com/"
    r"[^\s<>\"'\\]+|teams\.live\.com/[^\s<>\"'\\]+|zoom\.us/[jw]/[^\s<>\"'\\]+|meet\.jit\.si/"
    r"[^\s<>\"'\\]+|meet\.google\.com/[^\s<>\"'\\]+|/b/[a-z0-9-]{3,}|/rooms/[^\s<>\"'\\]+/join)",
    re.I,
)
MAX_URL = 500


@dataclass
class Invitation:
    """Ein Termin aus einer Einladung."""

    method: str
    uid: str
    sequence: int
    organizer: str
    title: str
    starts_at: datetime.datetime
    ends_at: datetime.datetime
    all_day: bool = False
    description: str = ""
    location: str = ""
    video_url: str = ""
    rrule: str = ""
    attendees: list[tuple[str, str]] = field(default_factory=list)  # (Adresse, PARTSTAT)

    def as_data(self) -> dict:
        """Zum Speichern am Eingang (JSON)."""
        return {
            "method": self.method,
            "uid": self.uid,
            "sequence": self.sequence,
            "organizer": self.organizer,
            "title": self.title,
            "starts_at": self.starts_at.isoformat(),
            "ends_at": self.ends_at.isoformat(),
            "all_day": self.all_day,
            "description": self.description,
            "location": self.location,
            "video_url": self.video_url,
            "rrule": self.rrule,
        }

    @classmethod
    def from_data(cls, data: dict) -> Invitation:
        return cls(
            method=data["method"],
            uid=data["uid"],
            sequence=int(data.get("sequence") or 0),
            organizer=data.get("organizer", ""),
            title=data.get("title", ""),
            starts_at=datetime.datetime.fromisoformat(data["starts_at"]),
            ends_at=datetime.datetime.fromisoformat(data["ends_at"]),
            all_day=bool(data.get("all_day")),
            description=data.get("description", ""),
            location=data.get("location", ""),
            video_url=data.get("video_url", ""),
            rrule=data.get("rrule", ""),
        )


class NotUsable(Exception):
    """Kalenderteil vorhanden, aber nicht übernehmbar (Grund für den Absender)."""


def calendar_part(msg: EmailMessage) -> str | None:
    """Text des Kalenderteils einer Mail oder ``None`` (keine Einladung).

    Gesucht wird ``text/calendar`` im Text oder als Anhang und ``.ics``-Dateien (manche
    Programme schicken ``application/ics``)."""
    for part in msg.walk():
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        name = (part.get_filename() or "").lower()
        if ctype not in ("text/calendar", "application/ics") and not name.endswith(".ics"):
            continue
        data = part.get_payload(decode=True) or b""
        if not data or len(data) > MAX_ICS:
            continue
        charset = part.get_content_charset() or "utf-8"
        try:
            text = data.decode(charset, errors="replace")
        except LookupError:
            text = data.decode("utf-8", errors="replace")
        if "BEGIN:VCALENDAR" in text.upper():
            return text
    return None


def is_tnef_invitation(msg: EmailMessage) -> bool:
    """Besprechungsanfrage von Outlook im Sonderformat (winmail.dat) statt iCalendar?"""
    content_class = str(msg.get("Content-Class", "") or "").lower()
    if "calendarmessage" not in content_class:
        return False
    for part in msg.walk():
        if part.get_content_type() == "application/ms-tnef":
            return True
        if (part.get_filename() or "").lower() == "winmail.dat":
            return True
    return False


def _method(text: str) -> str:
    for line in external._lines(text):
        name, _, value = external._split(line)
        if name == "METHOD":
            return value.strip().upper()
        if name == "BEGIN" and value.strip().upper() == "VEVENT":
            break
    return ""


def _address(value: str) -> str:
    value = value.strip()
    if value.lower().startswith("mailto:"):
        value = value[7:]
    return parseaddr(value)[1].strip().lower()


def _raw_vevents(text: str) -> list[list[str]]:
    """Zeilen je VEVENT (auch mehrfach vorkommende wie ATTENDEE)."""
    result, current, depth = [], None, 0
    for line in external._lines(text):
        upper = line.upper()
        if upper == "BEGIN:VEVENT":
            current, depth = [], 0
            continue
        if current is None:
            continue
        if upper.startswith("BEGIN:"):
            depth += 1
            continue
        if upper.startswith("END:"):
            if upper == "END:VEVENT" and depth == 0:
                result.append(current)
                current = None
            else:
                depth = max(0, depth - 1)
            continue
        if not depth:
            current.append(line)
    return result


def video_link(*texts: str) -> str:
    """Erster Konferenzlink (Talk, Jitsi, BigBlueButton, Teams, Zoom, Meet) in den Texten."""
    for text in texts:
        found = VIDEO_LINK.search(text or "")
        if found and len(found.group(0)) <= MAX_URL:
            return found.group(0).rstrip(".,;)")
    return ""


def read(text: str) -> Invitation:
    """Den Termin einer Einladung lesen. Wirft ``NotUsable`` mit verständlichem Grund."""
    method = _method(text) or "PUBLISH"
    if method not in METHODS:
        raise NotUsable(f"Kalenderteil mit {method} wird nicht übernommen.")
    raw = _raw_vevents(text)
    events = external._vevents(text)
    if not events:
        raise NotUsable("Die Einladung enthält keinen Termin.")
    if len(events) > 1:
        raise NotUsable(
            "Die Einladung enthält mehrere Termine (Serie mit Ausnahmen). "
            "Bitte solche Serien in HUBIplan anlegen."
        )
    ev, lines = events[0], raw[0]
    uid = external._unescape(ev.get("UID", ({}, ""))[1]).strip()[:255]
    if not uid:
        raise NotUsable("Der Einladung fehlt die Kennung (UID).")
    try:
        sequence = int(ev.get("SEQUENCE", ({}, "0"))[1].strip() or 0)
    except ValueError:
        sequence = 0
    organizer = _address(ev.get("ORGANIZER", ({}, ""))[1])
    attendees = []
    for line in lines:
        name, params, value = external._split(line)
        if name == "ATTENDEE":
            attendees.append((_address(value), params.get("PARTSTAT", "").upper()))
    if method == "REPLY":
        start = timezone.now()
        return Invitation(method, uid, sequence, organizer, "", start, start, attendees=attendees)
    if "DTSTART" not in ev:
        raise NotUsable("Der Einladung fehlt der Beginn.")
    parsed = external._ical_time(ev["DTSTART"][1], ev["DTSTART"][0])
    if parsed is None:
        raise NotUsable("Der Beginn der Einladung ist nicht lesbar.")
    start, all_day = parsed
    end = None
    if "DTEND" in ev:
        p_end = external._ical_time(ev["DTEND"][1], ev["DTEND"][0])
        end = p_end[0] if p_end else None
    elif "DURATION" in ev:
        delta = external._duration(ev["DURATION"][1])
        end = start + delta if delta else None
    if all_day:
        end = end - datetime.timedelta(days=1) if end and end > start else start
    if end is None or end < start:
        end = start if all_day else start + datetime.timedelta(hours=1)
    description = external._unescape(ev.get("DESCRIPTION", ({}, ""))[1]).strip()[:5000]
    location = external._unescape(ev.get("LOCATION", ({}, ""))[1]).strip()
    conference = ""
    for line in lines:
        name, _, value = external._split(line)
        if name in ("CONFERENCE", "X-GOOGLE-CONFERENCE", "X-MICROSOFT-SKYPETEAMSMEETINGURL"):
            conference = conference or value.strip()
    url = ev.get("URL", ({}, ""))[1].strip()
    video = ""
    if conference.lower().startswith("https://") and len(conference) <= MAX_URL:
        video = conference
    video = video or video_link(url, location, description)
    if video and location.strip() == video:
        location = ""  # Ort war nur der Link (Nextcloud: „Talk-Raum hinzufügen“)
    title = external._unescape(ev.get("SUMMARY", ({}, ""))[1]).strip()[:200]
    return Invitation(
        method=method,
        uid=uid,
        sequence=sequence,
        organizer=organizer,
        title=title or "Termin",
        starts_at=start,
        ends_at=end,
        all_day=all_day,
        description=description,
        location=location[:200],
        video_url=video,
        rrule=ev.get("RRULE", ({}, ""))[1].strip(),
        attendees=attendees,
    )


# --- Antwortadresse für HUBIplans eigene Einladungen (W1b) ---


def _code_mac(event_id: int, membership_id: int) -> str:
    key = f"events.imip-reply:{settings.SECRET_KEY}".encode()
    mac = hmac.new(key, f"{event_id}.{membership_id}".encode(), hashlib.sha256).hexdigest()
    return mac[:12]


def reply_code(event_id: int, membership_id: int) -> str:
    """Kurz genug für den Teil vor dem @ (höchstens 64 Zeichen)."""
    return f"{event_id}-{membership_id}-{_code_mac(event_id, membership_id)}"


def parse_reply_code(value: str) -> tuple[int, int] | None:
    found = re.fullmatch(r"(\d{1,12})-(\d{1,12})-([0-9a-f]{12})", (value or "").lower())
    if not found:
        return None
    event_id, membership_id = int(found.group(1)), int(found.group(2))
    if not hmac.compare_digest(found.group(3), _code_mac(event_id, membership_id)):
        return None
    return event_id, membership_id


def reply_domain() -> str:
    """Domain der Antwortadresse: die erste Verteiler-Domain, wenn Mails dort ankommen."""
    from circulars import inbound

    if not settings.INBOUND_IMAP_HOST:
        return ""
    found = inbound.domains()
    return found[0] if found else ""


def reply_address(event_id: int, membership_id: int) -> str:
    domain = reply_domain()
    if not domain:
        return ""
    return f"{REPLY_LOCAL}+{reply_code(event_id, membership_id)}@{domain}"


def code_in(addresses: list[str]) -> tuple[int, int] | None:
    """Antwortcode aus den Empfängeradressen (``termin+<code>@…``)."""
    from circulars import inbound

    accepted = set(inbound.domains())
    for address in addresses:
        local, _, domain = address.lower().rpartition("@")
        if domain not in accepted or "+" not in local:
            continue
        name, _, code = local.partition("+")
        if name == REPLY_LOCAL:
            parsed = parse_reply_code(code)
            if parsed:
                return parsed
    return None


# --- Kalenderteile schreiben ---


def _calendar(method: str, body: list[str]) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//hubiplan//Termineinladung//DE",
        "CALSCALE:GREGORIAN",
        f"METHOD:{method}",
        *body,
        "END:VCALENDAR",
    ]
    folded: list[str] = []
    for line in lines:
        folded.extend(_fold(line))
    return "\r\n".join(folded) + "\r\n"


def _times(starts_at, ends_at, all_day: bool) -> list[str]:
    if all_day:
        first = timezone.localtime(starts_at).date()
        last = timezone.localtime(ends_at).date() + datetime.timedelta(days=1)
        return [f"DTSTART;VALUE=DATE:{first:%Y%m%d}", f"DTEND;VALUE=DATE:{last:%Y%m%d}"]
    return [f"DTSTART:{_utc(starts_at)}", f"DTEND:{_utc(ends_at)}"]


def reply(invitation: Invitation, attendee: str, name: str = "") -> str:
    """``METHOD:REPLY`` „angenommen“ des Verteilers an den Organisator."""
    cn = f";CN={_quote(name)}" if name else ""
    body = [
        "BEGIN:VEVENT",
        f"UID:{_escape(invitation.uid)}",
        f"SEQUENCE:{invitation.sequence}",
        f"DTSTAMP:{_utc(timezone.now())}",
        *_times(invitation.starts_at, invitation.ends_at, invitation.all_day),
        f"SUMMARY:{_escape(invitation.title)}",
        f"ORGANIZER:mailto:{invitation.organizer}",
        f"ATTENDEE;PARTSTAT=ACCEPTED{cn}:mailto:{attendee}",
        "END:VEVENT",
    ]
    return _calendar("REPLY", body)


def _quote(value: str) -> str:
    return '"' + value.replace('"', "'").replace("\n", " ")[:100] + '"'


def sequence_of(event) -> int:
    """Wächst mit jeder Änderung (Sekunden seit dem Anlegen bis zur letzten Änderung)."""
    created = event.created_at or event.updated_at or timezone.now()
    updated = event.updated_at or created
    return max(0, int((updated - created).total_seconds()))


def invitation(event, uid: str, attendee: str, attendee_name: str, organizer: str) -> str:
    """Kalenderteil einer HUBIplan-Einladung (``REQUEST``) oder Absage (``CANCEL``).

    ``uid`` ist dieselbe Kennung wie im Kalender-Abo; so führen Programme, die beides
    sehen, die Einträge zusammen. ``organizer`` ist die Antwortadresse."""
    cancelled = event.is_cancelled
    owner = event.department.name if event.department_id else event.organization.name
    place = ", ".join(p for p in (event.location, event.address) if p)
    body = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"SEQUENCE:{sequence_of(event)}",
        f"DTSTAMP:{_utc(timezone.now())}",
        *_times(event.starts_at, event.ends_at, event.all_day),
        f"SUMMARY:{_escape(event.title)}",
    ]
    if place:
        body.append(f"LOCATION:{_escape(place)}")
    if event.description:
        body.append(f"DESCRIPTION:{_escape(event.description[:3000])}")
    video = getattr(event, "video_url", "")
    if video:
        body.append(f"URL:{video}")
    body += [
        f"ORGANIZER;CN={_quote(owner)}:mailto:{organizer}",
        f"ATTENDEE{';CN=' + _quote(attendee_name) if attendee_name else ''};ROLE=REQ-PARTICIPANT;"
        f"PARTSTAT=NEEDS-ACTION;RSVP={'FALSE' if cancelled else 'TRUE'}:mailto:{attendee}",
        f"STATUS:{'CANCELLED' if cancelled else 'CONFIRMED'}",
        "TRANSP:OPAQUE",
        "END:VEVENT",
    ]
    return _calendar("CANCEL" if cancelled else "REQUEST", body)


PARTSTATS = {"ACCEPTED": "yes", "DECLINED": "no", "TENTATIVE": "maybe"}
