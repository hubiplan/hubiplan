"""Belegung auf der Webseite (konzepte/infrastruktur.md, Abschnitt 5).

Je Objekt bestimmt ``booking_rules.website``, was die Webseite zeigt: ``off`` nichts,
``busy`` nur belegte Zeiten, ``titles`` zusätzlich den Zweck öffentlicher Buchungen.
Namen von Buchenden und Kontaktdaten erscheinen nie.
"""

from __future__ import annotations

import datetime

from django.utils import timezone
from django.utils.translation import gettext as _

from .models import BookingSlot
from .rules import rules_of

AREAS = {"material": "material", "facility": "infrastructure"}
DAYS_AHEAD = 180


def items(site):
    """Objekte, deren Belegung die Webseite zeigen darf."""
    from materials.models import MaterialItem

    modules = set(site.area.enabled_modules or [])
    kinds = [kind for kind, module in AREAS.items() if module in modules]
    qs = MaterialItem.objects.filter(
        organization=site.area,
        department_id=site.org.pk if site.is_unit else None,
        kind__in=kinds,
        deleted_at__isnull=True,
        booking_rules__enabled=True,
        booking_rules__website__in=["busy", "titles"],
    ).exclude(condition="retired")
    return sorted(qs, key=lambda i: (i.kind != "facility", i.facility_id or i.pk, i.pk))


def available(site) -> bool:
    return bool(items(site))


def occurrences(site, start, end, shown=None):
    shown = shown if shown is not None else items(site)
    by_id = {i.pk: i for i in shown}
    rows = []
    slots = (
        BookingSlot.objects.filter(
            resource_id__in=by_id,
            confirmed=True,
            starts_at__lt=end,
            ends_at__gt=start,
        )
        .select_related("booking")
        .order_by("starts_at", "pk")
    )
    for slot in slots[:2000]:
        booking = slot.booking
        item = by_id[slot.resource_id]
        titles = rules_of(item)["website"] == "titles" and booking.visibility == "public"
        rows.append(
            {
                "item": item,
                "key": f"{booking.pk}-{slot.resource_id}-{slot.original_start:%Y%m%dT%H%M%S}",
                "title": booking.title if titles else _("Belegt"),
                "starts_at": slot.starts_at,
                "ends_at": slot.ends_at,
                "all_day": booking.all_day,
            }
        )
    return rows


def window(start_text: str | None, days: int):
    from zoneinfo import ZoneInfo

    berlin = ZoneInfo("Europe/Berlin")
    try:
        start = datetime.date.fromisoformat(start_text) if start_text else timezone.localdate()
    except ValueError:
        start = timezone.localdate()
    begin = datetime.datetime.combine(start, datetime.time(), berlin)
    return begin, begin + datetime.timedelta(days=days)


def calendar(site, host: str) -> bytes:
    """iCal-Abo der öffentlichen Belegung (nur „belegt“ bzw. öffentliche Zwecke)."""
    from events.ical import _escape, _fold, _utc

    now = timezone.now()
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//hubiplan//Belegung//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(site.org.name + ' · ' + _('Belegung'))}",
        "X-WR-TIMEZONE:Europe/Berlin",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
    ]
    stamp = _utc(now)
    for row in occurrences(
        site, now - datetime.timedelta(days=7), now + datetime.timedelta(days=DAYS_AHEAD)
    ):
        lines += [
            "BEGIN:VEVENT",
            f"UID:belegung-{row['key']}@{host}",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{_utc(row['starts_at'])}",
            f"DTEND:{_utc(row['ends_at'])}",
            f"SUMMARY:{_escape(row['item'].title + ': ' + row['title'])}",
            "TRANSP:OPAQUE",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    folded = [part for line in lines for part in _fold(line)]
    return ("\r\n".join(folded) + "\r\n").encode()
