"""Voreinstellungen und Anlegen von Versammlungen."""

import datetime

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from events.models import Event

from .models import AgendaItem, Meeting, MeetingKind, agenda_numbers


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
                        "motion_days": 7 if base == MeetingKind.Base.GENERAL else None,
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
        items = [(a.title, a.type, a.description, a.level) for a in previous.agenda.all()]
    else:
        items = [(name, type_, "", 0) for name, type_ in default_agenda(kind)]
    numbers = agenda_numbers([entry[3] for entry in items])
    AgendaItem.objects.bulk_create(
        AgendaItem(
            organization=scope.org,
            meeting=meeting,
            position=index,
            level=level,
            number=number,
            title=name,
            type=type_,
            description=description,
        )
        for index, ((name, type_, description, _level), (level, number)) in enumerate(
            zip(items, numbers, strict=True), start=1
        )
    )
    return meeting


# --- Einladung (Schritt V2) ---------------------------------------------------------------


def invitation_filters(meeting) -> tuple[str, dict]:
    """Empfänger der Einladung als Auswahl eines Rundschreibens (Zielgruppe, Filter)."""
    from circulars.models import Circular
    from organizations.models import DepartmentRole

    kind = meeting.kind
    if meeting.organization.type == "federation":
        return Circular.Audience.BOARDS, {}
    if kind.base == MeetingKind.Base.GENERAL:
        filters = {}
        if kind.voter_types:
            filters["member_types"] = list(kind.voter_types)
        if kind.voter_min_age:
            filters["age_min"] = kind.voter_min_age
            # Das Mindestalter gilt nicht für Organisationsmitglieder (J4)
            filters["organizations_any_age"] = True
        return Circular.Audience.MEMBERS, filters
    if meeting.department_id is not None:
        roles = DepartmentRole.objects.filter(department_id=meeting.department_id)
        return Circular.Audience.MEMBERS, {"roles": sorted(roles.values_list("pk", flat=True))}
    return Circular.Audience.MEMBERS, {"board": True}


def invitation_text(meeting) -> tuple[str, str]:
    """Betreff und Text der Einladung mit Tagesordnung (im Rundschreiben noch änderbar)."""
    from core.i18n import date_text

    event = meeting.event
    start = timezone.localtime(event.starts_at)
    subject = _("Einladung: {title} am {date}").format(title=event.title, date=date_text(start))
    place = ", ".join(p for p in (event.location, event.address) if p)
    lines = [
        "{Anrede},",
        "",
        _("hiermit laden wir zur **{title}** ein.").format(title=event.title),
        "",
        _("**Wann:** {date}, {time} Uhr").format(date=date_text(start), time=f"{start:%H:%M}"),
    ]
    if place:
        lines.append(_("**Wo:** {place}").format(place=place))
    lines += ["", _("**Tagesordnung**"), ""]
    agenda = list(meeting.agenda.all())
    # Mit Unterpunkten (8.1) passt keine einfache nummerierte Liste mehr: dann „TOP 8.1: …“
    nested = any(item.level for item in agenda)
    for index, item in enumerate(agenda, start=1):
        if nested:
            entry = _("TOP {n}: {title}").format(n=item.number, title=item.title)
        else:
            entry = f"{index}. {item.title}"
        if item.description:
            entry += " – " + " ".join(item.description.split())
        lines.append(entry)
    lines += ["", _("Mit freundlichen Grüßen")]
    lines.append(_("Die Leitung") if meeting.department_id else _("Der Vorstand"))
    return subject[:200], "\n".join(lines)


@transaction.atomic
def prepare_invitation(meeting, user):
    """Rundschreiben-Entwurf mit Einladung anlegen (oder den vorhandenen Entwurf liefern)."""
    from circulars.models import Circular

    if meeting.circular_id and meeting.circular.status == Circular.Status.DRAFT:
        return meeting.circular
    audience, filters = invitation_filters(meeting)
    subject, body = invitation_text(meeting)
    circular = Circular.objects.create(
        organization=meeting.organization,
        department_id=meeting.department_id,
        kind=Circular.Kind.NOTICE,
        audience=audience,
        subject=subject,
        body=body,
        filters=filters,
        created_by=user,
    )
    meeting.circular = circular
    meeting.version += 1
    meeting.save(update_fields=["circular", "version", "updated_at"])
    return circular


def circular_sent(circular) -> None:
    """Nach dem Versand gilt die Versammlung als eingeladen."""
    from circulars.models import Circular

    if circular.status == Circular.Status.DRAFT:
        return
    for meeting in Meeting.objects.filter(circular=circular, status=Meeting.Status.DRAFT):
        meeting.status = Meeting.Status.INVITED
        meeting.invited_at = circular.sent_at or timezone.now()
        meeting.version += 1
        meeting.save(update_fields=["status", "invited_at", "version", "updated_at"])


# --- Anwesenheit (Schritt V3) ---------------------------------------------------------------


def voters(meeting):
    """Stimmberechtigte Mitgliedschaften (heute), nach derselben Auswahl wie die Einladung."""
    from circulars.recipients import club_base, club_filtered
    from members.models import Membership
    from organizations.models import Department

    if meeting.organization.type != "club":
        return Membership.objects.none()
    department = Department.objects.get(pk=meeting.department_id) if meeting.department_id else None
    _audience, filters = invitation_filters(meeting)
    base = club_base(meeting.organization, department)
    matched, _jubilees = club_filtered(meeting.organization, base, filters)
    return matched


def quorum(meeting, voter_count: int, counted: int) -> dict:
    """Beschlussfähigkeit nach der Art: nötige Zahl und ob sie erreicht ist."""
    import math

    kind = meeting.kind
    needed = 0
    if kind.quorum_percent:
        needed = math.ceil(voter_count * kind.quorum_percent / 100)
    if kind.quorum_count:
        needed = max(needed, kind.quorum_count)
    return {"needed": needed, "reached": counted >= needed, "rule": bool(needed)}
