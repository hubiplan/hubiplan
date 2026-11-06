"""Voreinstellungen und Anlegen von Versammlungen."""

import datetime

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from events.models import Event

from .models import AgendaItem, Meeting, MeetingKind


def _default_kinds(department_id):
    if department_id is not None:
        return [
            (_("Versammlung"), MeetingKind.Base.GENERAL, 7, MeetingKind.MinutesFor.VOTERS),
            (_("Sitzung der Leitung"), MeetingKind.Base.BOARD, 3, MeetingKind.MinutesFor.BOARD),
        ]
    return [
        (_("Jahreshauptversammlung"), MeetingKind.Base.GENERAL, 14, MeetingKind.MinutesFor.VOTERS),
        (
            _("Außerordentliche Mitgliederversammlung"),
            MeetingKind.Base.GENERAL,
            14,
            MeetingKind.MinutesFor.VOTERS,
        ),
        (_("Vorstandssitzung"), MeetingKind.Base.BOARD, 7, MeetingKind.MinutesFor.BOARD),
    ]


def kinds(scope):
    """Arten dieses Datenbereichs; beim ersten Aufruf mit Voreinstellungen angelegt."""
    qs = MeetingKind.objects.filter(organization=scope.org, department_id=scope.department_id)
    if not qs.exists():
        with transaction.atomic():
            for position, (name, base, days, minutes_for) in enumerate(
                _default_kinds(scope.department_id)
            ):
                MeetingKind.objects.get_or_create(
                    organization=scope.org,
                    department_id=scope.department_id,
                    name=name,
                    defaults={
                        "base": base,
                        "invite_days": days,
                        "minutes_for": minutes_for,
                        "position": position,
                    },
                )
    return qs.order_by("position", "name", "pk")


def default_agenda(kind):
    """Übliche Tagesordnung, wenn es noch keine frühere Versammlung dieser Art gibt."""
    if kind.base != MeetingKind.Base.GENERAL:
        return [
            (_("Begrüßung"), AgendaItem.Type.OTHER),
            (_("Genehmigung des letzten Protokolls"), AgendaItem.Type.RESOLUTION),
            (_("Verschiedenes"), AgendaItem.Type.OTHER),
        ]
    return [
        (_("Begrüßung und Feststellung der Beschlussfähigkeit"), AgendaItem.Type.OTHER),
        (_("Genehmigung der Tagesordnung"), AgendaItem.Type.RESOLUTION),
        (_("Genehmigung des Protokolls der letzten Versammlung"), AgendaItem.Type.RESOLUTION),
        (_("Berichte des Vorstands"), AgendaItem.Type.REPORT),
        (_("Kassenbericht"), AgendaItem.Type.REPORT),
        (_("Bericht der Kassenprüfer"), AgendaItem.Type.REPORT),
        (_("Entlastung des Vorstands"), AgendaItem.Type.RESOLUTION),
        (_("Wahlen"), AgendaItem.Type.ELECTION),
        (_("Anträge"), AgendaItem.Type.RESOLUTION),
        (_("Verschiedenes"), AgendaItem.Type.OTHER),
    ]


def invite_by(meeting) -> datetime.date:
    """Letzter Tag, an dem die Einladung nach der Frist der Art hinausgehen muss."""
    start = timezone.localdate(meeting.event.starts_at)
    return start - datetime.timedelta(days=meeting.kind.invite_days)


@transaction.atomic
def create(scope, user, *, kind, title, starts_at, ends_at, location, address, agenda_from_last):
    event = Event.objects.create(
        organization=scope.org,
        department_id=scope.department_id,
        title=title,
        location=location,
        address=address,
        starts_at=starts_at,
        ends_at=ends_at,
        visibility=Event.Visibility.BOARD
        if kind.base == MeetingKind.Base.BOARD
        else Event.Visibility.MEMBERS,
        created_by=user,
    )
    meeting = Meeting.objects.create(
        organization=scope.org,
        department_id=scope.department_id,
        kind=kind,
        event=event,
        created_by=user,
    )
    previous = None
    if agenda_from_last:
        previous = (
            Meeting.objects.filter(
                organization=scope.org, department_id=scope.department_id, kind=kind
            )
            .exclude(pk=meeting.pk)
            .order_by("-event__starts_at", "-pk")
            .first()
        )
    if previous is not None:
        items = [(a.title, a.type, a.description) for a in previous.agenda.all()]
    else:
        items = [(name, type_, "") for name, type_ in default_agenda(kind)]
    AgendaItem.objects.bulk_create(
        AgendaItem(
            organization=scope.org,
            meeting=meeting,
            position=index,
            title=name,
            type=type_,
            description=description,
        )
        for index, (name, type_, description) in enumerate(items, start=1)
    )
    return meeting
