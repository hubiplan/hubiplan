"""Anmelden per App und Online-Abstimmung (Schritt V7).

Die Leitung öffnet die Anmeldung; ihre Seite zeigt einen QR-Code, der alle 30 Sekunden
wechselt. Mitglieder scannen ihn mit der App oder der Kamera (Mitgliederbereich) und melden
sich so an; „Ich gehe“ meldet ab. Erlaubt die Art die Teilnahme aus der Ferne und hat die
Leitung sie für die Versammlung eingeschaltet, geht die Anmeldung auch ohne Code.

Abstimmen dürfen anwesende Stimmberechtigte, für jede Vollmacht eine Stimme mehr, ebenso
der Vertreter eines Organisationsmitglieds, wenn er selbst Mitglied ist. Bei geheimen
Abstimmungen trägt der Stimmzettel keine Person und keinen Zeitpunkt; wer abgestimmt hat,
steht getrennt davon.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from . import services
from .models import Attendance, Ballot, Meeting, Poll, PollOption, Resolution, VoteCast

# Ein Code gilt für dieses Zeitfenster und das vorige (also 30 bis 60 Sekunden)
WINDOW = 30
# Stände, in denen angemeldet und abgestimmt werden kann
LIVE_STATES = (Meeting.Status.DRAFT, Meeting.Status.INVITED, Meeting.Status.HELD)
MAX_POLLS = 60
MAX_CANDIDATES = 20


def _window(now: float | None = None) -> int:
    return int((now if now is not None else time.time()) // WINDOW)


def _sign(meeting: Meeting, window: int) -> str:
    digest = hmac.new(
        meeting.checkin_key.encode(), f"{meeting.pk}:{window}".encode(), hashlib.sha256
    ).hexdigest()
    return f"{window}-{digest[:16]}"


def current_code(meeting: Meeting) -> dict:
    """Aktueller Code für den QR-Code der Leitung und Sekunden bis zum nächsten Wechsel."""
    now = time.time()
    window = _window(now)
    return {
        "code": _sign(meeting, window),
        "refresh_in": max(1, int((window + 1) * WINDOW - now)),
    }


def code_valid(meeting: Meeting, code: str) -> bool:
    if not meeting.checkin_open or not meeting.checkin_key or not code:
        return False
    window = _window()
    return any(hmac.compare_digest(_sign(meeting, w), str(code)) for w in (window, window - 1))


def open_checkin(meeting: Meeting, *, open_: bool, remote: bool | None) -> None:
    if meeting.status not in LIVE_STATES:
        raise ValidationError({"detail": _("Die Anmeldung ist jetzt nicht mehr möglich.")})
    meeting.checkin_open = open_
    if open_ and not meeting.checkin_key:
        meeting.checkin_key = secrets.token_urlsafe(32)
    if not open_:
        # Neuer Schlüssel beim nächsten Öffnen: alte Fotos des Codes gelten nicht mehr
        meeting.checkin_key = ""
    if remote is not None:
        if remote and not meeting.kind.remote_allowed:
            raise ValidationError(
                {"remote": _("Bei dieser Art ist keine Teilnahme aus der Ferne vorgesehen.")}
            )
        meeting.remote = remote
    meeting.save(update_fields=["checkin_open", "checkin_key", "remote", "updated_at"])


# --- Anmelden und Abmelden --------------------------------------------------------------


def _record(meeting: Meeting, membership) -> Attendance:
    from .views import person_name

    record_, _created = Attendance.objects.get_or_create(
        meeting=meeting,
        membership=membership,
        defaults={
            "organization": meeting.organization,
            "name": person_name(membership),
            "status": Attendance.Status.PRESENT,
        },
    )
    return record_


def check_in(meeting: Meeting, membership, *, mode: str) -> Attendance:
    """Mitglied als anwesend eintragen (per Code im Saal oder aus der Ferne)."""
    from .views import unconfirm

    if membership.person.is_organization:
        raise ValidationError(
            {"detail": _("Organisationsmitglieder trägt die Leitung mit ihrem Vertreter ein.")}
        )
    voter_ids = set(services.voters(meeting).values_list("pk", flat=True))
    if mode == Attendance.Mode.ONLINE and membership.pk not in voter_ids:
        raise ValidationError(
            {"detail": _("Aus der Ferne teilnehmen können nur Stimmberechtigte.")}
        )
    record_ = _record(meeting, membership)
    record_.status = Attendance.Status.PRESENT
    record_.mode = mode
    record_.voter = membership.pk in voter_ids
    record_.represented_by = None
    record_.delegate_name = ""
    record_.delegate_membership = None
    record_.save()
    unconfirm(meeting)
    return record_


def check_out(meeting: Meeting, membership) -> None:
    from .views import unconfirm

    record_ = meeting.attendance.filter(membership=membership).first()
    if record_ is None or record_.status != Attendance.Status.PRESENT:
        return
    record_.status = Attendance.Status.LEFT
    record_.save()
    # Wer geht, vertritt niemanden mehr (wie in der Liste von Hand)
    record_.proxies.update(status=Attendance.Status.EXCUSED, represented_by=None)
    unconfirm(meeting)


# --- Stimmen ----------------------------------------------------------------------------


def entitlements(meeting: Meeting, membership_id: int, voter_ids: set[int] | None = None):
    """Stimmen, die dieses Mitglied abgeben darf: eigene, Vollmachten, Organisationen."""
    if voter_ids is None:
        voter_ids = set(services.voters(meeting).values_list("pk", flat=True))
    records = list(meeting.attendance.all())
    me = next((r for r in records if r.membership_id == membership_id), None)
    result: list[tuple[Attendance, str]] = []
    if me and me.status == Attendance.Status.PRESENT:
        if me.membership_id in voter_ids:
            result.append((me, "own"))
        result += [
            (r, "proxy")
            for r in records
            if r.status == Attendance.Status.REPRESENTED
            and r.represented_by_id == me.pk
            and r.membership_id in voter_ids
        ]
    result += [
        (r, "delegate")
        for r in records
        if r.status == Attendance.Status.DELEGATE
        and r.delegate_membership_id == membership_id
        and r.membership_id in voter_ids
    ]
    return me, result


def entitled_count(meeting: Meeting, voter_ids: set[int]) -> int:
    """Alle Stimmen, die abgegeben werden könnten (anwesend, vertreten, durch Vertreter)."""
    return sum(
        1
        for r in meeting.attendance.all()
        if r.membership_id in voter_ids
        and r.status
        in (
            Attendance.Status.PRESENT,
            Attendance.Status.REPRESENTED,
            Attendance.Status.DELEGATE,
        )
    )


def create_poll(meeting: Meeting, item, *, question: str, secret: bool, office: str, candidates):
    if not meeting.kind.online_voting:
        raise ValidationError(
            {"detail": _("Bei dieser Art ist keine Online-Abstimmung vorgesehen.")}
        )
    if meeting.status not in LIVE_STATES:
        raise ValidationError({"detail": _("Abstimmungen sind jetzt nicht mehr möglich.")})
    if meeting.polls.count() >= MAX_POLLS:
        raise ValidationError({"detail": _("Zu viele Abstimmungen in dieser Versammlung.")})
    kind = (
        Resolution.Kind.ELECTION if item.type == item.Type.ELECTION else Resolution.Kind.RESOLUTION
    )
    question = question.strip() or item.title
    names = [c for c in candidates if (c.get("name") or "").strip()]
    if len(names) > MAX_CANDIDATES:
        raise ValidationError({"candidates": _("Zu viele Personen zur Wahl.")})
    if kind == Resolution.Kind.ELECTION and not names:
        raise ValidationError({"candidates": _("Bitte mindestens eine Person zur Wahl angeben.")})
    poll = Poll.objects.create(
        organization=meeting.organization,
        meeting=meeting,
        agenda_item=item,
        kind=kind,
        question=question,
        office=office.strip() if kind == Resolution.Kind.ELECTION else "",
        secret=secret,
    )
    options: list[tuple[str, str, int | None]] = []
    if kind == Resolution.Kind.ELECTION and len(names) > 1:
        options = [("candidate", c["name"].strip(), c.get("membership")) for c in names]
        options.append(("abstain", _("Enthaltung"), None))
    else:
        options = [
            ("yes", _("Ja"), None),
            ("no", _("Nein"), None),
            ("abstain", _("Enthaltung"), None),
        ]
        if names:
            # Eine Person zur Wahl: Ja/Nein/Enthaltung, die Person steht bei „Ja“
            options[0] = ("yes", _("Ja"), names[0].get("membership"))
            poll.candidate = names[0]["name"].strip()
            poll.save(update_fields=["candidate"])
    from members.models import Membership

    valid = set(
        Membership.objects.filter(
            organization=meeting.organization,
            pk__in=[m for _r, _l, m in options if m],
        ).values_list("pk", flat=True)
    )
    PollOption.objects.bulk_create(
        PollOption(
            organization=meeting.organization,
            meeting=meeting,
            poll=poll,
            position=i,
            role=role,
            label=label,
            membership_id=m if m in valid else None,
        )
        for i, (role, label, m) in enumerate(options)
    )
    return poll


def set_poll_status(poll: Poll, status: str) -> None:
    meeting = poll.meeting
    if status == Poll.Status.OPEN:
        if poll.status != Poll.Status.DRAFT:
            raise ValidationError({"detail": _("Die Abstimmung wurde schon gestartet.")})
        if meeting.status not in LIVE_STATES:
            raise ValidationError({"detail": _("Abstimmungen sind jetzt nicht mehr möglich.")})
        poll.status = Poll.Status.OPEN
        poll.opened_at = timezone.now()
    elif status == Poll.Status.CLOSED:
        if poll.status != Poll.Status.OPEN:
            raise ValidationError({"detail": _("Die Abstimmung läuft nicht.")})
        voter_ids = set(services.voters(meeting).values_list("pk", flat=True))
        poll.status = Poll.Status.CLOSED
        poll.closed_at = timezone.now()
        poll.entitled = entitled_count(meeting, voter_ids)
    else:
        raise ValidationError({"status": _("Unbekannter Stand.")})
    poll.save(update_fields=["status", "opened_at", "closed_at", "entitled"])


def cast(poll: Poll, membership_id: int, votes: list[dict]) -> None:
    """Stimmen abgeben: je Eintrag ``attendance`` (eigene oder vertretene Stimme), ``option``."""
    if poll.status != Poll.Status.OPEN:
        raise ValidationError({"detail": _("Die Abstimmung läuft nicht.")})
    me, allowed = entitlements(poll.meeting, membership_id)
    allowed_ids = {r.pk for r, _how in allowed}
    options = {o.pk: o for o in poll.options.all()}
    if not votes:
        raise ValidationError({"detail": _("Bitte eine Antwort wählen.")})
    seen = set()
    for vote in votes:
        attendance_id = vote.get("attendance")
        if attendance_id not in allowed_ids or attendance_id in seen:
            raise ValidationError({"detail": _("Für diese Stimme bist du nicht berechtigt.")})
        if vote.get("option") not in options:
            raise ValidationError({"detail": _("Unbekannte Antwort.")})
        seen.add(attendance_id)
    try:
        with transaction.atomic():
            for vote in votes:
                VoteCast.objects.create(
                    organization=poll.organization,
                    meeting=poll.meeting,
                    poll=poll,
                    attendance_id=vote["attendance"],
                    cast_by=me,
                )
            # Geheime Stimmzettel in zufälliger Reihenfolge und ohne Person
            ballots = [
                Ballot(
                    organization=poll.organization,
                    meeting=poll.meeting,
                    poll=poll,
                    option=options[vote["option"]],
                    attendance_id=None if poll.secret else vote["attendance"],
                )
                for vote in votes
            ]
            secrets.SystemRandom().shuffle(ballots)
            Ballot.objects.bulk_create(ballots)
    except IntegrityError:
        raise ValidationError({"detail": _("Für diese Stimme wurde schon abgestimmt.")}) from None


def option_label(option: PollOption) -> str:
    """Ja, Nein und Enthaltung in der Sprache der Person, die die Abstimmung sieht."""
    if option.role == PollOption.Role.CANDIDATE:
        return option.label
    return str(PollOption.Role(option.role).label)


def tally(poll: Poll) -> list[dict]:
    counts: dict[int, int] = {}
    for option_id in poll.ballots.values_list("option_id", flat=True):
        counts[option_id] = counts.get(option_id, 0) + 1
    return [
        {"id": o.pk, "role": o.role, "label": option_label(o), "votes": counts.get(o.pk, 0)}
        for o in poll.options.all()
    ]


def apply_result(poll: Poll) -> Resolution:
    """Ergebnis einer beendeten Abstimmung als Beschluss oder Wahl übernehmen."""
    from .views import unconfirm

    if poll.status != Poll.Status.CLOSED:
        raise ValidationError({"detail": _("Die Abstimmung ist noch nicht beendet.")})
    meeting = poll.meeting
    if meeting.status == Meeting.Status.DONE or meeting.status == Meeting.Status.CANCELLED:
        raise ValidationError({"detail": _("Das Protokoll lässt sich nicht mehr ändern.")})
    rows = tally(poll)
    abstain = sum(r["votes"] for r in rows if r["role"] == "abstain")
    resolution = poll.resolution or Resolution(
        organization=meeting.organization,
        meeting=meeting,
        agenda_item=poll.agenda_item,
        position=poll.agenda_item.resolutions.count(),
    )
    resolution.kind = poll.kind
    resolution.unanimous = False
    resolution.votes_abstain = abstain
    candidates = [r for r in rows if r["role"] == "candidate"]
    if candidates:
        best = max(r["votes"] for r in candidates)
        winners = [r for r in candidates if r["votes"] == best]
        winner = winners[0] if len(winners) == 1 and best > 0 else None
        resolution.votes_yes = winner["votes"] if winner else 0
        resolution.votes_no = sum(r["votes"] for r in candidates) - resolution.votes_yes
        resolution.result = Resolution.Result.ACCEPTED if winner else Resolution.Result.REJECTED
        option = next((o for o in poll.options.all() if winner and o.pk == winner["id"]), None)
        resolution.elected_name = winner["label"] if winner else ""
        resolution.elected_id = option.membership_id if option else None
        resolution.text = poll.question
    else:
        yes = next(r["votes"] for r in rows if r["role"] == "yes")
        no = next(r["votes"] for r in rows if r["role"] == "no")
        resolution.votes_yes, resolution.votes_no = yes, no
        resolution.result = Resolution.Result.ACCEPTED if yes > no else Resolution.Result.REJECTED
        resolution.text = poll.question
        if poll.kind == Resolution.Kind.ELECTION:
            option = next(o for o in poll.options.all() if o.role == "yes")
            accepted = resolution.result == Resolution.Result.ACCEPTED
            resolution.elected_name = poll.candidate if accepted else ""
            resolution.elected_id = option.membership_id if accepted else None
    resolution.office = poll.office
    resolution.save()
    poll.resolution = resolution
    poll.save(update_fields=["resolution"])
    unconfirm(meeting)
    return resolution


def poll_data(poll: Poll, *, voter_ids: set[int], for_membership: int | None = None) -> dict:
    """Abstimmung für Leitung (``for_membership`` None) oder ein Mitglied."""
    casts = list(poll.casts.all())
    data = {
        "id": poll.pk,
        "agenda_item": poll.agenda_item_id,
        "agenda_position": poll.agenda_item.position,
        "agenda_number": poll.agenda_item.number,
        "agenda_title": poll.agenda_item.title,
        "kind": poll.kind,
        "question": poll.question,
        "office": poll.office,
        "candidate": poll.candidate,
        "secret": poll.secret,
        "status": poll.status,
        "opened_at": poll.opened_at,
        "closed_at": poll.closed_at,
        "cast": len(casts),
        "entitled": (
            poll.entitled
            if poll.status == Poll.Status.CLOSED
            else entitled_count(poll.meeting, voter_ids)
        ),
        "options": [
            {"id": o.pk, "role": o.role, "label": option_label(o)} for o in poll.options.all()
        ],
        # Ergebnis erst nach dem Ende, damit niemand beeinflusst wird
        "result": tally(poll) if poll.status == Poll.Status.CLOSED else None,
        "resolution": poll.resolution_id,
    }
    if for_membership is not None:
        _me, allowed = entitlements(poll.meeting, for_membership, voter_ids)
        done = {c.attendance_id for c in casts}
        data["votes"] = [
            {"attendance": r.pk, "name": r.name, "how": how, "done": r.pk in done}
            for r, how in allowed
        ]
    elif not poll.secret and poll.status == Poll.Status.CLOSED:
        names = {r.pk: r.name for r in poll.meeting.attendance.all()}
        labels = {o.pk: option_label(o) for o in poll.options.all()}
        data["open_votes"] = sorted(
            (
                {"name": names.get(b.attendance_id, ""), "option": labels.get(b.option_id, "")}
                for b in poll.ballots.all()
            ),
            key=lambda v: v["name"].lower(),
        )
    return data
