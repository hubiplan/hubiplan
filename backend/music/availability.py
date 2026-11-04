"""Bekannte Konflikte im eigenen Verein, ohne private Kalenderinhalte auszugeben."""

import datetime

from django.utils import timezone
from django.utils.translation import gettext
from rest_framework.exceptions import ValidationError

from events import recurrence
from events.models import EventResponse

from .models import Assignment, MusicianAbsence, RehearsalInvitation


def interval(event, starts=None, ends=None):
    start = starts if starts is not None else event.starts_at
    end = ends if ends is not None else event.ends_at
    if event.all_day:
        end = timezone.localtime(end) + datetime.timedelta(days=1)
    start, end = start.astimezone(datetime.UTC), end.astimezone(datetime.UTC)
    return start, max(end, start + datetime.timedelta(microseconds=1))


def performance_interval(performance):
    start, end = interval(performance.event)
    start = min(t for t in (start, performance.meeting_at, performance.setup_at) if t is not None)
    return start.astimezone(datetime.UTC), end


class Availability:
    """Eine Zeitspanne für mehrere Musiker mit wenigen gemeinsamen Abfragen prüfen."""

    def __init__(self, org, musicians, event, start, end):
        musicians = list(musicians)
        ids = [m.pk for m in musicians]
        self.flags = {pk: set() for pk in ids}
        if not ids:
            return

        def overlaps(a, b):
            return a < end and start < b

        for pk in MusicianAbsence.objects.filter(
            organization=org, musician_id__in=ids, starts_at__lt=end, ends_at__gt=start
        ).values_list("musician_id", flat=True):
            self.flags[pk].add("absence")
        for row in (
            Assignment.objects.filter(
                organization=org,
                musician_id__in=ids,
                status__in=["pending", "accepted"],
                performance__event__is_cancelled=False,
            )
            .exclude(performance__event_id=event.pk)
            .select_related("performance__event")
        ):
            if overlaps(*performance_interval(row.performance)):
                self.flags[row.musician_id].add("busy")

        expanded = {}

        def occurrences(other):
            if other.pk not in expanded:
                expanded[other.pk] = [
                    o
                    for o in recurrence.occurrences(
                        [other],
                        start - datetime.timedelta(days=1),
                        end + datetime.timedelta(days=1),
                    )
                    if not o.is_cancelled and overlaps(*interval(other, o.starts_at, o.ends_at))
                ]
            return expanded[other.pk]

        for invite in (
            RehearsalInvitation.objects.filter(
                organization=org,
                musician_id__in=ids,
                active=True,
                rehearsal__event__is_cancelled=False,
            )
            .exclude(rehearsal__event_id=event.pk)
            .select_related("rehearsal__event")
            .prefetch_related("responses")
        ):
            declined = {
                r.original_start.astimezone(datetime.UTC)
                for r in invite.responses.all()
                if r.status == "declined"
            }
            if any(
                o.original_start.astimezone(datetime.UTC) not in declined
                for o in occurrences(invite.rehearsal.event)
            ):
                self.flags[invite.musician_id].add("busy")
        members = {m.membership_id: m.pk for m in musicians if m.membership_id}
        for row in EventResponse.objects.filter(
            organization=org, membership_id__in=members, event__is_cancelled=False
        ).select_related("event"):
            if row.event_id == event.pk:
                if row.status == "no":
                    self.flags[members[row.membership_id]].add("declined")
            elif row.status == "yes" and occurrences(row.event):
                self.flags[members[row.membership_id]].add("busy")

    def reasons(self, musician):
        return sorted(self.flags.get(musician.pk, set()))


def ensure_available(musician, event, start, end):
    if not musician.active:
        raise ValidationError(gettext("Dieser Musiker ist inaktiv."))
    if Availability(musician.organization, [musician], event, start, end).reasons(musician):
        raise ValidationError(
            gettext(
                "Für diesen Musiker liegt eine Abwesenheit, Absage oder Terminüberschneidung vor."
            )
        )


def ensure_performance(musician, performance):
    if performance.event.is_cancelled:
        raise ValidationError(gettext("Dieser Auftritt ist abgesagt."))
    ensure_available(musician, performance.event, *performance_interval(performance))
