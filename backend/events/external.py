"""Fremde Kalender abholen: Vereinsplaner (öffentliche Schnittstelle) und iCal-Abos.

Ablauf je Kalender (``sync``):
1. Termine von außen holen (``fetch_vereinsplaner`` bzw. ``fetch_ical``), alle über
   ``core.safehttp`` (keine internen Adressen, keine Weiterleitungen).
2. Jeden Termin über ``remote_uid`` anlegen oder aktualisieren. Termine, die die Quelle
   nicht mehr liefert oder die hier ausgeblendet sind, verschwinden.
3. Fehler stehen am Kalender; die Termine vom letzten Abruf bleiben dann stehen.

Übernommen wird ein Zeitfenster von 90 Tagen zurück bis zwei Jahre voraus. Serien aus
iCal werden zu einzelnen Terminen (wie in unseren eigenen Abos). Zu- und Absagen,
Erinnerungen und E-Mails gibt es für fremde Termine nicht.

Alle Aufrufe nach außen laufen über ``_get`` (in Tests ersetzt).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import urllib.parse
import zoneinfo
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext

from core import safehttp

from .models import Event, ExternalCalendar

log = logging.getLogger(__name__)

VEREINSPLANER_URL = "https://api.vereinsplaner.com/public/v1/resources/public-events"
PER_PAGE = 100
MAX_PAGES = 30
MAX_EVENTS = 1000
MAX_ICAL = 4 * 1024 * 1024
MAX_JSON = 2 * 1024 * 1024
PAST = datetime.timedelta(days=90)
AHEAD = datetime.timedelta(days=730)
TIMEOUT = 20


class ExternalError(Exception):
    """Quelle nicht erreichbar, Zugang abgelehnt oder Antwort unbrauchbar."""


@dataclass
class Item:
    key: str
    title: str
    starts_at: datetime.datetime
    ends_at: datetime.datetime
    all_day: bool = False
    description: str = ""
    location: str = ""
    address: str = ""
    is_cancelled: bool = False


def berlin() -> zoneinfo.ZoneInfo:
    return zoneinfo.ZoneInfo("Europe/Berlin")


def window() -> tuple[datetime.datetime, datetime.datetime]:
    now = timezone.now()
    return now - PAST, now + AHEAD


# --- HTTP (in Tests ersetzt) ---


def _get(url: str, headers: dict, max_body: int) -> tuple[int, bytes]:
    try:
        resp = safehttp.request(
            "GET",
            url,
            headers={"User-Agent": "HUBIplan", **headers},
            timeout=TIMEOUT,
            max_body=max_body,
        )
    except safehttp.SafeHTTPError as exc:
        raise ExternalError(str(exc)) from exc
    if len(resp.body) > max_body:
        raise ExternalError(gettext("Die Antwort ist zu groß."))
    return resp.status, resp.body


# --- Vereinsplaner ---


def _vp_time(value) -> datetime.datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if timezone.is_naive(parsed):
        parsed = parsed.replace(tzinfo=berlin())
    return parsed


def _day_start(moment: datetime.datetime) -> datetime.datetime:
    day = moment.astimezone(berlin()).date()
    return datetime.datetime.combine(day, datetime.time(), tzinfo=berlin())


def _vp_item(data: dict) -> Item | None:
    if not isinstance(data, dict):
        return None
    uid = str(data.get("uuid") or "")[:40]
    start = _vp_time(data.get("start"))
    end = _vp_time(data.get("end")) or start
    if not uid or start is None:
        return None
    if end < start:
        end = start
    all_day = bool(data.get("full_day"))
    if all_day:
        # Ganztägig wie bei uns: Beginn = erster Tag 0:00, Ende = letzter Tag 0:00
        start, end = _day_start(start), _day_start(end)
    text = str(data.get("description") or "").strip()
    category = str(data.get("category_name") or "").strip()
    deadline = _vp_time(data.get("register_until"))
    extras = []
    if category:
        extras.append(gettext("Kategorie: {name}").format(name=category))
    if deadline:
        extras.append(
            gettext("Anmeldung bis {date}").format(
                date=deadline.astimezone(berlin()).strftime("%d.%m.%Y %H:%M")
            )
        )
    if extras:
        text = "\n\n".join(filter(None, [text, " · ".join(extras)]))
    loc = data.get("location") if isinstance(data.get("location"), dict) else {}
    street = " ".join(filter(None, [loc.get("street"), loc.get("house_number")]))
    town = " ".join(filter(None, [loc.get("zip_code"), loc.get("city_name")]))
    return Item(
        key=uid,
        title=str(data.get("title") or "")[:200] or gettext("Termin"),
        starts_at=start,
        ends_at=end,
        all_day=all_day,
        description=text[:5000],
        location=str(loc.get("display_name") or "")[:200],
        address=", ".join(filter(None, [street, town]))[:300],
    )


def fetch_vereinsplaner(token: str, secret: str = "") -> list[Item]:
    headers = {"x-api-token": token, "Accept": "application/json"}
    if secret:
        headers["x-api-secret"] = secret
    items: list[Item] = []
    page, last = 1, 1
    while page <= min(last, MAX_PAGES):
        query = urllib.parse.urlencode({"page": page, "per_page": PER_PAGE})
        status, body = _get(f"{VEREINSPLANER_URL}?{query}", headers, MAX_JSON)
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ExternalError(
                gettext("Vereinsplaner hat keine gültige Antwort geschickt.")
            ) from exc
        if status in (401, 403):
            raise ExternalError(
                gettext("Vereinsplaner lehnt das Token ab ({status}).").format(status=status)
            )
        if status not in (200, 206) or not isinstance(data, dict) or not data.get("success"):
            message = str(data.get("message") or "")[:200] if isinstance(data, dict) else ""
            raise ExternalError(
                gettext("Vereinsplaner meldet einen Fehler ({status}). {message}")
                .format(status=status, message=message)
                .strip()
            )
        for raw in data.get("data") or []:
            item = _vp_item(raw)
            if item is not None:
                items.append(item)
        pagination = data.get("pagination") if isinstance(data.get("pagination"), dict) else {}
        try:
            last = int(pagination.get("last_page") or 1)
        except (TypeError, ValueError):
            last = 1
        page += 1
    return _dedupe(items)


def _dedupe(items: list[Item]) -> list[Item]:
    """Gleiche Kennung mehrfach (z. B. einzelne Termine einer Serie): Beginn anhängen."""
    seen: dict[str, int] = {}
    for item in items:
        seen[item.key] = seen.get(item.key, 0) + 1
    for item in items:
        if seen[item.key] > 1:
            item.key = f"{item.key}@{item.starts_at.astimezone(datetime.UTC):%Y%m%dT%H%M%S}"
    return items


# --- iCal ---


def _unescape(text: str) -> str:
    out, i = [], 0
    while i < len(text):
        char = text[i]
        if char == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            out.append("\n" if nxt in "nN" else nxt)
            i += 2
            continue
        out.append(char)
        i += 1
    return "".join(out)


def _lines(text: str) -> list[str]:
    """Zeilen entfalten (Folgezeilen beginnen mit Leerzeichen oder Tab)."""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw:
            lines.append(raw)
    return lines


def _split(line: str) -> tuple[str, dict, str]:
    head, _, value = line.partition(":")
    # Doppelpunkte in Parameterwerten (in Anführungszeichen) sind selten; dann neu teilen
    if head.count('"') % 2:
        quote_end = line.find('"', len(head) + 1)
        colon = line.find(":", quote_end)
        head, value = line[:colon], line[colon + 1 :]
    name, *params = head.split(";")
    parsed = {}
    for p in params:
        key, _, val = p.partition("=")
        parsed[key.upper()] = val.strip('"')
    return name.upper(), parsed, value


def _zone(params: dict) -> datetime.tzinfo:
    tzid = params.get("TZID", "")
    try:
        return zoneinfo.ZoneInfo(tzid) if tzid else berlin()
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return berlin()


def _ical_time(value: str, params: dict) -> tuple[datetime.datetime, bool] | None:
    value = value.strip()
    try:
        if params.get("VALUE") == "DATE" or (len(value) == 8 and value.isdigit()):
            day = datetime.datetime.strptime(value[:8], "%Y%m%d").date()
            return datetime.datetime.combine(day, datetime.time(), tzinfo=berlin()), True
        if value.endswith("Z"):
            parsed = datetime.datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
            return parsed.replace(tzinfo=datetime.UTC), False
        parsed = datetime.datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
        return parsed.replace(tzinfo=_zone(params)), False
    except ValueError:
        return None


def _duration(value: str) -> datetime.timedelta | None:
    import re

    m = re.fullmatch(
        r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", value.strip()
    )
    if not m:
        return None
    sign, w, d, h, mi, s = m.groups()
    delta = datetime.timedelta(
        weeks=int(w or 0),
        days=int(d or 0),
        hours=int(h or 0),
        minutes=int(mi or 0),
        seconds=int(s or 0),
    )
    return -delta if sign == "-" else delta


def _vevents(text: str) -> list[dict]:
    events, current, depth = [], None, 0
    for line in _lines(text):
        upper = line.upper()
        if upper == "BEGIN:VEVENT":
            current, depth = {"EXDATE": []}, 0
            continue
        if current is None:
            continue
        if upper.startswith("BEGIN:"):
            depth += 1  # z. B. VALARM: überspringen
            continue
        if upper.startswith("END:"):
            if upper == "END:VEVENT" and depth == 0:
                events.append(current)
                current = None
            else:
                depth = max(0, depth - 1)
            continue
        if depth:
            continue
        name, params, value = _split(line)
        if name == "EXDATE":
            for part in value.split(","):
                parsed = _ical_time(part, params)
                if parsed:
                    current["EXDATE"].append(parsed[0])
        elif name not in current:
            current[name] = (params, value)
    return events


def _expand(start, rule: str, exdates, length, since, until) -> list[datetime.datetime]:
    from dateutil.rrule import rrulestr

    try:
        rr = rrulestr(rule, dtstart=start)
        moments = rr.between(since - length, until, inc=True)
    except (ValueError, TypeError):
        return [start]
    excluded = {x.astimezone(datetime.UTC) for x in exdates}
    return [m for m in moments if m.astimezone(datetime.UTC) not in excluded][:MAX_EVENTS]


def parse_ical(text: str) -> list[Item]:
    since, until = window()
    items: dict[str, Item] = {}
    overrides: list[tuple[str, Item]] = []
    for ev in _vevents(text):
        if "DTSTART" not in ev:
            continue
        params, value = ev["DTSTART"]
        parsed = _ical_time(value, params)
        if parsed is None:
            continue
        start, all_day = parsed
        end = None
        if "DTEND" in ev:
            p_end = _ical_time(ev["DTEND"][1], ev["DTEND"][0])
            end = p_end[0] if p_end else None
        elif "DURATION" in ev:
            delta = _duration(ev["DURATION"][1])
            end = start + delta if delta else None
        if all_day:
            # iCal: DTEND ist der Tag danach; bei uns zählt der letzte Tag
            end = end - datetime.timedelta(days=1) if end and end > start else start
        length = (end - start) if end and end >= start else datetime.timedelta()
        uid = _unescape(ev.get("UID", ({}, ""))[1]).strip()
        title = _unescape(ev.get("SUMMARY", ({}, ""))[1]).strip()
        base = Item(
            key="",
            title=title[:200] or gettext("Termin"),
            starts_at=start,
            ends_at=start + length,
            all_day=all_day,
            description=_unescape(ev.get("DESCRIPTION", ({}, ""))[1]).strip()[:5000],
            location=_unescape(ev.get("LOCATION", ({}, ""))[1]).strip()[:200],
            is_cancelled=ev.get("STATUS", ({}, ""))[1].strip().upper() == "CANCELLED",
        )
        uid = uid or hashlib.sha256(f"{title}{value}".encode()).hexdigest()
        if "RECURRENCE-ID" in ev:
            rid = _ical_time(ev["RECURRENCE-ID"][1], ev["RECURRENCE-ID"][0])
            if rid:
                overrides.append((_occ_key(uid, rid[0]), base))
            continue
        if "RRULE" in ev:
            for moment in _expand(start, ev["RRULE"][1], ev["EXDATE"], length, since, until):
                item = Item(**{**base.__dict__})
                item.starts_at, item.ends_at = moment, moment + length
                item.key = _occ_key(uid, moment)
                items[item.key] = item
        else:
            base.key = _occ_key(uid, None)
            items[base.key] = base
    for key, item in overrides:
        item.key = key
        items[key] = item
    result = [i for i in items.values() if i.ends_at >= since and i.starts_at <= until]
    result.sort(key=lambda i: i.starts_at)
    return result[:MAX_EVENTS]


def _occ_key(uid: str, moment: datetime.datetime | None) -> str:
    raw = uid if moment is None else f"{uid}@{moment.astimezone(datetime.UTC):%Y%m%dT%H%M%S}"
    return hashlib.sha256(raw.encode()).hexdigest()[:40]


def fetch_ical(url: str) -> list[Item]:
    url = url.strip()
    if url.lower().startswith("webcal://"):
        url = "https://" + url[len("webcal://") :]
    status, body = _get(url, {"Accept": "text/calendar"}, MAX_ICAL)
    if status != 200:
        raise ExternalError(
            gettext("Der Kalender-Link antwortet mit {status}.").format(status=status)
        )
    text = body.decode("utf-8", errors="replace")
    if "BEGIN:VCALENDAR" not in text.upper():
        raise ExternalError(gettext("Unter dem Link liegt kein Kalender (iCal)."))
    return parse_ical(text)


# --- Abgleich ---


def fetch(cal: ExternalCalendar) -> list[Item]:
    from accounts.mfa import decrypt

    token = decrypt(cal.token) if cal.token else ""
    if not token:
        raise ExternalError(gettext("Es ist kein Zugang hinterlegt."))
    if cal.kind == ExternalCalendar.Kind.VEREINSPLANER:
        return fetch_vereinsplaner(token, decrypt(cal.secret) if cal.secret else "")
    return fetch_ical(token)


def hidden_keys(cal: ExternalCalendar) -> set[str]:
    return {h.get("key") for h in (cal.hidden or []) if isinstance(h, dict)}


def key_of(event: Event) -> str:
    prefix = f"ext:{event.external_source_id}:"
    return event.remote_uid[len(prefix) :] if event.remote_uid.startswith(prefix) else ""


def hide(event: Event) -> None:
    """Einen fremden Termin hier ausblenden; er bleibt es bei jedem Abruf."""
    cal = event.external_source
    key = key_of(event)
    if key and key not in hidden_keys(cal):
        cal.hidden = [
            *(cal.hidden or []),
            {"key": key, "title": event.title, "starts_at": event.starts_at.isoformat()},
        ]
        cal.save(update_fields=["hidden"])
    event.delete()


def uid_of(cal: ExternalCalendar, key: str) -> str:
    return f"ext:{cal.pk}:{key}"[:80]


def apply(cal: ExternalCalendar, items: list[Item]) -> int:
    """Kopien anlegen, ändern und entfernen; liefert die Zahl der Termine."""
    since, until = window()
    hidden = hidden_keys(cal)
    keep = set()
    for item in items[:MAX_EVENTS]:
        if item.key in hidden or item.ends_at < since or item.starts_at > until:
            continue
        values = {
            "title": item.title,
            "description": item.description,
            "location": item.location,
            "address": item.address,
            "all_day": item.all_day,
            "starts_at": item.starts_at,
            "ends_at": item.ends_at,
            "is_cancelled": item.is_cancelled,
            "category": cal.category,
            "visibility": cal.visibility,
            "share_up": False,
            "share_down": cal.share_down,
            "repeat": Event.Repeat.NONE,
            "rsvp_enabled": False,
            "remind_days": None,
        }
        event, created = Event.objects.get_or_create(
            organization=cal.organization,
            department=None,
            external_source=cal,
            remote_uid=uid_of(cal, item.key),
            defaults=values,
        )
        if not created:
            moved = (event.starts_at, event.ends_at, event.location) != (
                item.starts_at,
                item.ends_at,
                item.location,
            )
            changed = [k for k, v in values.items() if getattr(event, k) != v]
            if changed:
                for k in changed:
                    setattr(event, k, values[k])
                if moved:
                    event.changed_at = timezone.now()
                event.save()
        keep.add(event.pk)
    Event.objects.filter(external_source=cal).exclude(pk__in=keep).delete()
    return len(keep)


def sync(cal: ExternalCalendar) -> int:
    """Einen Kalender abholen; Fehler stehen danach am Kalender."""
    from core.tenancy import unit_context

    with unit_context(cal.organization_id):
        try:
            items = fetch(cal)
        except ExternalError as exc:
            cal.last_error = str(exc)[:500]
            cal.last_sync_at = timezone.now()
            cal.save(update_fields=["last_error", "last_sync_at"])
            return 0
        with transaction.atomic():
            count = apply(cal, items)
            cal.last_error = ""
            cal.last_sync_at = timezone.now()
            cal.save(update_fields=["last_error", "last_sync_at"])
        return count


def sync_all() -> int:
    from .services import module_on

    total = 0
    for cal in ExternalCalendar.objects.filter(is_active=True).select_related("organization"):
        if not module_on(cal.organization):
            continue
        try:
            total += sync(cal)
        except Exception:  # noqa: BLE001 – ein Kalender darf die anderen nicht aufhalten
            log.exception("Abruf des fremden Kalenders %s fehlgeschlagen", cal.pk)
    return total
