"""Belegungen ausrechnen, Konflikte prüfen und mit Terminen abgleichen."""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from dateutil import rrule
from django.db import IntegrityError, transaction
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import APIException

from .models import Booking, BookingSlot
from .rules import rules_of

BERLIN = ZoneInfo("Europe/Berlin")
FREQ = {"weekly": rrule.WEEKLY, "monthly": rrule.MONTHLY, "yearly": rrule.YEARLY}
# Serien werden höchstens so weit im Voraus ausgerechnet; tasks.extend_series rollt nach
HORIZON = datetime.timedelta(days=730)
MAX_PER_SERIES = 600


class Conflict(APIException):
    status_code = 409
    default_code = "conflict"

    def __init__(self, rows):
        super().__init__(
            {"detail": _("Das Objekt ist in dieser Zeit schon belegt."), "conflicts": rows}
        )


def occurrences(booking, start=None, end=None):
    """(ursprünglicher Beginn, Beginn, Ende) aller nicht ausgefallenen Vorkommen."""
    duration = booking.ends_at - booking.starts_at
    end = end or timezone.now() + HORIZON
    if not booking.is_series:
        starts = [booking.starts_at]
    else:
        local = timezone.localtime(booking.starts_at, BERLIN).replace(tzinfo=None)
        until = None
        if booking.repeat_until:
            until = datetime.datetime.combine(booking.repeat_until, datetime.time(23, 59, 59))
        limit = timezone.localtime(end, BERLIN).replace(tzinfo=None)
        if until is None or until > limit:
            until = limit
        rule = rrule.rrule(
            FREQ[booking.repeat],
            dtstart=local,
            interval=booking.repeat_interval,
            until=until,
            count=None,
        )
        starts = [d.replace(tzinfo=BERLIN) for d in rule[:MAX_PER_SERIES]]
    skipped = (
        set(booking.exceptions.values_list("original_start", flat=True)) if booking.pk else set()
    )
    result = []
    for begin in starts:
        if begin in skipped:
            continue
        if start and begin + duration <= start:
            continue
        result.append((begin, begin, begin + duration))
    return result


def resources(item):
    """Gebucht wird das Objekt selbst; ein Gebäude belegt dazu alle seine Bereiche."""
    rows = [item]
    if item.kind == "facility" and item.location_kind != "facility":
        rows += list(item.contents.filter(kind="facility", deleted_at__isnull=True))
    return rows


def _slots(booking, confirmed):
    rules = rules_of(booking.item)
    before = datetime.timedelta(minutes=rules["buffer_before"])
    after = datetime.timedelta(minutes=rules["buffer_after"])
    rows = []
    for original, begin, finish in occurrences(booking):
        for resource in resources(booking.item):
            rows.append(
                BookingSlot(
                    organization_id=booking.organization_id,
                    booking=booking,
                    resource=resource,
                    original_start=original,
                    starts_at=begin,
                    ends_at=finish,
                    period=DateTimeTZRange(begin - before, finish + after, "[)"),
                    confirmed=confirmed,
                )
            )
    return rows


def conflicts(booking, slots):
    """Bestätigte fremde Belegungen, die sich mit diesen Belegungen überschneiden."""
    found = {}
    for slot in slots:
        for other in (
            BookingSlot.objects.filter(
                resource=slot.resource, confirmed=True, period__overlap=slot.period
            )
            .exclude(booking=booking)
            .select_related("booking")[:5]
        ):
            found[(other.booking_id, other.original_start)] = {
                "booking": other.booking_id,
                "starts_at": other.starts_at,
                "ends_at": other.ends_at,
            }
        if len(found) >= 10:
            break
    return sorted(found.values(), key=lambda r: r["starts_at"])


def rebuild(booking, *, strict=True):
    """Belegungen neu schreiben. ``strict``: bei Überschneidung 409 statt Prüfhinweis."""
    BookingSlot.objects.filter(booking=booking).delete()
    if booking.status not in (Booking.Status.REQUESTED, Booking.Status.CONFIRMED):
        return
    confirmed = booking.status == Booking.Status.CONFIRMED
    rows = _slots(booking, confirmed)
    if confirmed:
        clash = conflicts(booking, rows)
        if clash:
            if strict:
                raise Conflict(clash)
            for row in rows:
                row.confirmed = False
            booking.needs_review = True
            booking.save(update_fields=["needs_review"])
    try:
        with transaction.atomic():
            BookingSlot.objects.bulk_create(rows)
    except IntegrityError as exc:
        # Gleichzeitig gebucht: die Datenbank hat die zweite Buchung abgewiesen
        if strict:
            raise Conflict(conflicts(booking, rows)) from exc
        for row in rows:
            row.confirmed = False
        BookingSlot.objects.bulk_create(rows)
        booking.needs_review = True
        booking.save(update_fields=["needs_review"])


def rebuild_for_item(item):
    """Nach geänderten Rüstzeiten oder Bereichen: künftige Buchungen neu ausrechnen."""
    from materials.models import MaterialItem

    targets = {item.pk}
    if item.kind == "facility" and item.facility_id:
        targets.add(item.facility_id)
    for target in MaterialItem.objects.filter(pk__in=targets):
        for booking in Booking.objects.filter(
            item=target, status__in=[Booking.Status.REQUESTED, Booking.Status.CONFIRMED]
        ).exclude(ends_at__lt=timezone.now(), repeat="none"):
            rebuild(booking, strict=False)


def copy_times(booking, source):
    """Zeiten und Wiederholung aus einem Termin übernehmen."""
    booking.starts_at = source.starts_at
    booking.ends_at = source.ends_at
    booking.all_day = source.all_day
    booking.repeat = source.repeat
    booking.repeat_interval = source.repeat_interval
    booking.repeat_until = source.repeat_until
    if booking.all_day:
        # Ganztägig: Termine enden am letzten Tag 0:00, die Belegung erst am Tagesende
        booking.ends_at = booking.ends_at + datetime.timedelta(days=1)


def competition_times(booking, competition):
    begin = datetime.datetime.combine(competition.date, datetime.time(0, 0), tzinfo=BERLIN)
    booking.starts_at = begin
    booking.ends_at = begin + datetime.timedelta(days=1)
    booking.all_day = True
    booking.repeat = "none"
    booking.repeat_interval = 1
    booking.repeat_until = None
