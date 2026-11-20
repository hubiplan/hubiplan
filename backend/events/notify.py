"""E-Mails zu Terminen: Einladung, Änderung oder Absage, Erinnerung.

Jede Mail geht einzeln an ein Mitglied (keine sichtbaren Adresslisten) und landet
im Postausgang des Vereins. Mitglieder ohne E-Mail-Adresse bekommen keine Mail;
für sie gibt es das gedruckte Jahresprogramm.
"""

from __future__ import annotations

import datetime
import logging

from django.conf import settings
from django.utils import timezone

from core.tenancy import rls_bypass
from organizations.addresses import base_url
from outbox import mail, rate

from . import maps, rsvp, rsvp_link
from .models import Event, EventResponse

logger = logging.getLogger(__name__)

INVITE = "invite"
CHANGE = "change"
CANCEL = "cancel"
REMIND = "remind"

KINDS = {
    INVITE: "Einladung",
    CHANGE: "Geänderter Termin",
    CANCEL: "Abgesagt",
    REMIND: "Erinnerung",
}


def when(event: Event) -> str:
    start = timezone.localtime(event.starts_at)
    end = timezone.localtime(event.ends_at)
    if event.all_day:
        if start.date() == end.date():
            return f"{start:%d.%m.%Y}, ganztägig"
        return f"{start:%d.%m.%Y} bis {end:%d.%m.%Y}"
    if start.date() == end.date():
        return f"{start:%d.%m.%Y}, {start:%H:%M} bis {end:%H:%M} Uhr"
    return f"{start:%d.%m.%Y}, {start:%H:%M} Uhr bis {end:%d.%m.%Y}, {end:%H:%M} Uhr"


def body(
    event: Event,
    kind: str,
    first_name: str,
    response: EventResponse | None,
    link: str = "",
    attached: list[str] | None = None,
    skipped: list[str] | None = None,
) -> str:
    owner = event.department.name if event.department_id else event.organization.name
    intro = {
        INVITE: f"{owner} lädt Sie zu folgendem Termin ein:",
        CHANGE: f"bei folgendem Termin von {owner} haben sich Zeit oder Ort geändert:",
        CANCEL: f"folgender Termin von {owner} ist abgesagt:",
        REMIND: f"eine Erinnerung an folgenden Termin von {owner}:",
    }[kind]
    lines = [f"Hallo {first_name},", "", intro, "", event.title, f"Wann: {when(event)}"]
    if event.location or event.address:
        lines.append(f"Wo: {', '.join(x for x in (event.location, event.address) if x)}")
    if kind != CANCEL:
        lines += maps.mail_lines(event)
    if kind == CANCEL and event.cancel_note:
        lines.append(f"Hinweis: {event.cancel_note}")
    if event.description and kind in (INVITE, REMIND):
        text = event.description.strip()
        lines += ["", text if len(text) <= 1500 else text[:1500] + " …"]
    if event.rsvp_enabled and kind != CANCEL:
        lines.append("")
        if response is not None:
            lines.append(f"Ihre Rückmeldung: {rsvp.response_label(response)}.")
        if not rsvp.deadline_passed(event):
            if event.rsvp_deadline:
                deadline = timezone.localtime(event.rsvp_deadline)
                lines.append(f"Rückmeldung bitte bis {deadline:%d.%m.%Y, %H:%M} Uhr.")
            if link:
                lines.append(f"Zu- oder absagen (ohne Anmeldung): {link}")
            else:
                base = base_url(event.organization)
                lines.append(f"Zu- oder absagen können Sie im Mitgliederbereich: {base}/termine")
    if attached:
        lines += ["", f"Anlagen: {', '.join(attached)}"]
    if skipped:
        where = "über den Link oben" if link else "im Mitgliederbereich"
        lines.append(f"Weitere Anlagen ({', '.join(skipped)}) finden Sie {where}.")
    lines += ["", "Viele Grüße", owner]
    return "\n".join(lines) + "\n"


def subject(event: Event, kind: str) -> str:
    start = timezone.localtime(event.starts_at)
    return f"{KINDS[kind]}: {event.title} am {start:%d.%m.%Y}"


def recipients(event: Event, kind: str):
    """Mitgliedschaften, die die Mail bekommen."""
    members = rsvp.invited(event).prefetch_related("person__contacts")
    if kind == REMIND and event.rsvp_enabled:
        # Erinnert werden nur, die zugesagt haben oder noch unsicher sind
        members = members.filter(
            event_responses__event=event,
            event_responses__status__in=[EventResponse.Status.YES, EventResponse.Status.MAYBE],
        )
    elif kind in (CHANGE, CANCEL) and event.rsvp_enabled:
        # Absager brauchen keine Nachricht
        members = members.exclude(
            event_responses__event=event, event_responses__status=EventResponse.Status.NO
        )
    return members


# Stundengrenze erreicht: Rest so viel später (wie bei Rundschreiben)
RATE_RETRY_SECONDS = 10 * 60


def send(event_id: int, kind: str, remaining: list[int] | None = None) -> int:
    """Verschickt die Mails. Gibt die Zahl der verschickten Mails zurück.

    Mit Stundengrenze (``MAIL_RATE_PER_HOUR``, Gesamtaudit 15.11., PF-09) geht nur so viel
    hinaus, wie die Grenze erlaubt; der Rest folgt später mit der Liste der noch offenen
    Mitgliedschaften (``remaining``). Wer schon eine Mail bekam, steht nicht mehr darin."""
    with rls_bypass():
        event = (
            Event.objects.select_related("organization", "department").filter(pk=event_id).first()
        )
        if event is None or kind not in KINDS:
            return 0
        first = remaining is None
        if first:
            remaining = list(
                dict.fromkeys(recipients(event, kind).order_by("pk").values_list("pk", flat=True))
            )
        responses = {r.membership_id: r for r in event.responses.all()}
        with_link = rsvp_link.offers_link(event) and kind != CANCEL
        # Anhänge gehen mit der Einladung mit (wie bei Rundschreiben)
        stored, skipped = rsvp_link.mail_attachments(event) if kind == INVITE else ([], [])
        members = {
            m.pk: m
            for m in rsvp.invited(event)
            .filter(pk__in=remaining)
            .select_related("person")
            .prefetch_related("person__contacts")
        }
        sent = 0
        left = list(remaining)
        with mail.connection():
            while left:
                membership = members.get(left[0])
                address = rsvp.email_of(membership) if membership else ""
                if not address:
                    left.pop(0)
                    continue
                if not rate.take():
                    break
                left.pop(0)
                ok = mail.send(
                    address,
                    subject(event, kind),
                    body(
                        event,
                        kind,
                        membership.person.first_name,
                        responses.get(membership.pk),
                        link=rsvp_link.url(event, membership.pk) if with_link else "",
                        attached=[a["name"] for a in stored],
                        skipped=skipped,
                    ),
                    organization=event.organization,
                    kind="termin",
                    stored_attachments=stored or None,
                    fail_silently=True,
                    calendar=_calendar(event, kind, membership, address),
                )
                sent += int(ok)
        if left and not settings.CELERY_TASK_ALWAYS_EAGER:
            logger.info("Termin %s: Stundengrenze, %s Mails folgen später", event_id, len(left))
            from .tasks import send_event_mails

            send_event_mails.apply_async((event_id, kind, left), countdown=RATE_RETRY_SECONDS)
        if first and kind in (INVITE, REMIND):
            try:
                push_app(event, kind, [m.pk for m in recipients(event, kind)])
            except Exception:  # Push ist Zugabe: Mails sind schon unterwegs
                logger.exception("Push zum Termin %s gescheitert", event_id)
    logger.info("Termin %s: %s Mails (%s)", event_id, sent, kind)
    return sent


def _calendar(event: Event, kind: str, membership, address: str):
    """Kalenderteil für „Annehmen/Ablehnen“ im Mailprogramm (W1b), nicht bei Erinnerungen."""
    if kind == REMIND:
        return None
    from .mail_intake import calendar_for

    try:
        return calendar_for(event, membership.pk, address, membership.person.first_name)
    except Exception:  # noqa: BLE001 – Zugabe; die Mail geht auch ohne
        logger.exception("Kalenderteil zum Termin %s nicht erzeugt", event.pk)
        return None


def push_app(event: Event, kind: str, membership_ids: list[int]) -> int:
    """Einladung oder Erinnerung auch als Push an die App (mit Zu- und Absage)."""
    from devices.push import app_accesses, send_to_user
    from portal.models import PortalAccess

    accesses = app_accesses(membership_ids)
    if not accesses:
        return 0
    users = dict(PortalAccess.objects.filter(pk__in=accesses.values()).values_list("pk", "user_id"))
    where = ", ".join(x for x in (event.location, event.address) if x)
    text = when(event) + (f" · {where}" if where else "")
    base = {
        "v": 1,
        "t": "event",
        "id": event.pk,
        "kind": kind,
        "title": subject(event, kind)[:200],
        "text": text[:300],
        "from": event.department.name if event.department_id else event.organization.name,
    }
    if rsvp_link.offers_link(event):
        base["rsvp"] = True
        if event.rsvp_maybe:
            base["maybe"] = True
    pushed = 0
    for access_id in accesses.values():
        user_id = users.get(access_id)
        if user_id:
            pushed += int(send_to_user(user_id, {**base, "access": access_id}) > 0)
    return pushed


def due_reminders(now: datetime.datetime | None = None) -> list[int]:
    """Termine, deren Erinnerung jetzt fällig ist."""
    now = now or timezone.now()
    with rls_bypass():
        candidates = Event.objects.filter(
            remind_days__isnull=False,
            reminded_at__isnull=True,
            is_cancelled=False,
            repeat=Event.Repeat.NONE,
            starts_at__gt=now,
            starts_at__lte=now + datetime.timedelta(days=61),
        ).only("pk", "starts_at", "remind_days")
        return [
            e.pk for e in candidates if e.starts_at - datetime.timedelta(days=e.remind_days) <= now
        ]


def send_reminders(now: datetime.datetime | None = None) -> int:
    now = now or timezone.now()
    total = 0
    for pk in due_reminders(now):
        with rls_bypass():
            # Erst vermerken, dann senden: lieber eine Erinnerung zu wenig als doppelt
            claimed = Event.objects.filter(pk=pk, reminded_at__isnull=True).update(reminded_at=now)
        if claimed:
            total += send(pk, REMIND)
    return total
