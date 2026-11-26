"""Termine aus dem Mailprogramm: Einladungen an einen Verteiler werden Termine (W1).

Wer in Outlook, Thunderbird, Nextcloud oder am Handy einen Termin anlegt und als
Teilnehmer eine Verteileradresse einlädt (z. B. ``vorstand@…``), schickt eine Mail mit
Kalenderteil (iMIP, ``events.imip``). Der Abruf des Verteiler-Sammelpostfachs
(``circulars.inbound``) gibt solche Mails hierher statt an das Rundschreiben:

1. Absender: ein Konto mit dem Terminrecht der Einheit des Verteilers (und, falls
   eingestellt, unter den Absendern des Verteilers). „Jeder darf schreiben“ gilt für
   Termine nicht; Fremde werden still verworfen. Nextcloud verschickt Einladungen von
   einer eigenen Adresse; dann zählt der Organisator, wenn er als Antwort-an steht.
2. Bestätigung: Der Absender bekommt einen Link (wie beim Rundschreiben). Nur im Modus
   „direkt“ und mit bestandener DMARC-Prüfung des Absenders selbst wird sofort übernommen.
3. Übernehmen (``apply``): neuer Termin, Änderung (gleiche Kennung, höhere Fassung) oder
   Absage. Sichtbarkeit nach dem Empfängerkreis des Verteilers: Rolleninhaber → „nur
   Vorstand“, sonst „Mitglieder“; nie automatisch öffentlich.
4. Einladung: ein Rundschreiben nach dem Muster des Verteilers mit Wann, Wo, Videolink
   und (bei Mitgliederterminen) Rückmeldelink. Videolink aus der Einladung oder, wenn der
   Verteiler es so will, ein neuer Talk-Raum (``oidc.nc_talk``).
5. Der Organisator bekommt „angenommen“ (``METHOD:REPLY``) und eine Mail mit dem Ergebnis.

Antworten auf HUBIplans eigene Einladungen (W1b) verarbeitet ``handle_reply``.
"""

from __future__ import annotations

import datetime
import logging
import re
import uuid
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers

from audit.log import record
from core import virenscan
from core.tenancy import rls_bypass
from organizations.addresses import base_url
from organizations.platform_public import instance_name
from outbox import mail

from . import imip
from .models import MAX_ATTACHMENT_BYTES, MAX_ATTACHMENTS, Event, EventAttachment, EventResponse

logger = logging.getLogger(__name__)

NEW = "new"
UPDATE = "update"
CANCEL = "cancel"
ACTIONS = {NEW: "neuer Termin", UPDATE: "geänderter Termin", CANCEL: "Absage"}

# Empfängerkreise des Verteilers, die einen Termin „nur Vorstand“ ergeben
BOARD_AUDIENCES = ("roles", "boards", "departments")
SERIES = {"WEEKLY": "weekly", "MONTHLY": "monthly", "YEARLY": "yearly"}
WEEKDAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


# --- Wer darf ---


def has_right(user, ml) -> bool:
    """Terminrecht für die Einheit des Verteilers."""
    from access.catalog import DEPT_EVENTS_MANAGE, EVENTS_MANAGE
    from access.permissions import permissions_in
    from portal.services import department_contexts

    if user is None or not user.is_active:
        return False
    with rls_bypass():
        if EVENTS_MANAGE in permissions_in(user, ml.organization):
            return True
        if ml.department_id:
            ctx = department_contexts(user).get(ml.department_id)
            return ctx is not None and DEPT_EVENTS_MANAGE in ctx.permissions
    return False


def may_send(user, ml) -> bool:
    if not has_right(user, ml):
        return False
    with rls_bypass():
        chosen = list(ml.senders.values_list("pk", flat=True))
    return not chosen or user.pk in chosen


def sender_of(msg: EmailMessage, invitation: imip.Invitation) -> tuple[str, bool]:
    """Wessen Konto zählt, und ob die Mail von ihm selbst kommt (nicht über Nextcloud)."""
    sender = parseaddr(str(msg.get("From", "") or ""))[1].lower()
    organizer = invitation.organizer
    if not organizer or sender == organizer:
        return sender, True
    replies = [a.lower() for _, a in getaddresses([str(v) for v in msg.get_all("Reply-To") or []])]
    if organizer in replies:
        # Nextcloud und andere Kalenderserver: „Name (via Nextcloud)“ <noreply@…>
        return organizer, False
    return sender, True


# --- Einladung prüfen ---


def is_own_or_bounce(msg: EmailMessage) -> str:
    """Nur das Nötigste (Kalenderserver schicken oft von „noreply“-Adressen)."""
    from outbox.backend import ORG_HEADER

    if msg.get(ORG_HEADER):
        return "Mail von HUBIplan selbst"
    if str(msg.get("Return-Path", "") or "").strip() == "<>":
        return "Rückläufer"
    if msg.get_content_type() == "multipart/report":
        return "Rückläufer"
    return ""


def series_of(invitation: imip.Invitation) -> dict:
    """Wiederholung der Einladung in HUBIplans Form; wirft ``NotUsable``, wenn es nicht passt."""
    if not invitation.rrule:
        return {}
    parts = dict(
        p.split("=", 1) for p in invitation.rrule.upper().split(";") if "=" in p and p.strip()
    )
    freq = parts.pop("FREQ", "")
    hint = "Diese Wiederholung kennt HUBIplan nicht; bitte die Serie in HUBIplan anlegen."
    if freq not in SERIES:
        raise imip.NotUsable(hint)
    start = timezone.localtime(invitation.starts_at)
    if (
        freq == "WEEKLY"
        and parts.get("BYDAY", WEEKDAYS[start.weekday()]) == WEEKDAYS[start.weekday()]
    ):
        parts.pop("BYDAY", None)
    if freq == "MONTHLY" and parts.get("BYMONTHDAY", str(start.day)) == str(start.day):
        parts.pop("BYMONTHDAY", None)
    parts.pop("WKST", None)
    interval = parts.pop("INTERVAL", "1")
    until_raw, count = parts.pop("UNTIL", ""), parts.pop("COUNT", "")
    if parts or not interval.isdigit() or not 1 <= int(interval) <= 52:
        raise imip.NotUsable(hint)
    result = {"repeat": SERIES[freq], "repeat_interval": int(interval), "repeat_until": None}
    if until_raw:
        parsed = imip.external._ical_time(until_raw, {})
        if parsed is None:
            raise imip.NotUsable(hint)
        result["repeat_until"] = timezone.localtime(parsed[0]).date()
    elif count.isdigit():
        import itertools

        from dateutil.rrule import rrulestr

        n = min(int(count), 500)
        if n <= 0:
            raise imip.NotUsable(hint)
        moments = list(itertools.islice(rrulestr(invitation.rrule, dtstart=start), n))
        if moments:
            result["repeat_until"] = moments[-1].date()
    return result


def visibility_for(ml) -> str:
    audience = ml.pattern.audience if ml.pattern_id else "members"
    if audience in BOARD_AUDIENCES:
        return Event.Visibility.BOARD
    return Event.Visibility.MEMBERS


def find_event(ml, uid: str) -> Event | None:
    with rls_bypass():
        return (
            Event.objects.filter(
                organization=ml.organization, department=ml.department, mail_uid=uid
            )
            .select_related("organization", "department")
            .order_by("-pk")
            .first()
        )


# --- Anhänge bis zur Bestätigung ---


def _stash_pdfs(msg: EmailMessage, org) -> tuple[list[dict], list[str]]:
    """PDF-Anhänge der Einladung geprüft im privaten Speicher ablegen."""
    from core import crypto
    from exchange.models import private_storage

    files, skipped, total = [], [], 0
    for part in msg.iter_attachments():
        name = (part.get_filename() or "").strip()
        if not name or name.lower().endswith(".ics") or part.get_content_type() == "text/calendar":
            continue
        name = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1][:200]
        data = part.get_payload(decode=True) or b""
        if not data.startswith(b"%PDF-"):
            skipped.append(f"{name} (nur PDF möglich)")
            continue
        if len(data) > MAX_ATTACHMENT_BYTES or total + len(data) > 2 * MAX_ATTACHMENT_BYTES:
            skipped.append(f"{name} (zu groß)")
            continue
        if len(files) >= MAX_ATTACHMENTS:
            skipped.append(f"{name} (höchstens {MAX_ATTACHMENTS} Anhänge)")
            continue
        if not virenscan.inbound_ok(data, name, "Termineinladung an Verteiler"):
            skipped.append(f"{name} (Schadsoftware gefunden)")
            continue
        total += len(data)
        with crypto.owner(org.pk):
            path = private_storage().save(
                f"events/eingang/{uuid.uuid4().hex}.pdf", ContentFile(data)
            )
        files.append({"name": name, "path": path, "size": len(data)})
    return files, skipped


def _drop_stash(entry) -> None:
    from exchange.models import private_storage

    for item in (entry.event_data or {}).get("files") or []:
        try:
            private_storage().delete(item["path"])
        except OSError:
            logger.warning("Termin-Eingang: Datei %s nicht löschbar", item.get("path"))


# --- Eingang ---


def handle(msg: EmailMessage, text: str | None, ml, base: dict):
    """Mail mit Kalenderteil an einen Verteiler verarbeiten. Gibt den Eingang zurück."""
    from circulars import inbound
    from circulars.models import InboundMail

    rejected = InboundMail.Status.REJECTED
    reason = is_own_or_bounce(msg)
    if reason:
        return inbound._log(**base, status=rejected, reason=f"Verworfen: {reason}.")
    if inbound.dmarc_failed(msg):
        return inbound._log(**base, status=rejected, reason="Absender nicht echt (DMARC-Prüfung).")
    if text is None:
        # Outlook-Sonderformat: nur wer darf, bekommt eine Erklärung
        user = inbound.user_for(base["sender"])
        reason = (
            "Outlook hat die Einladung als „winmail.dat“ geschickt. Bitte in Outlook unter "
            "Datei › Optionen › E-Mail das Nachrichtenformat „HTML“ wählen (nicht „Rich-Text“) "
            "und die Einladung erneut senden."
        )
        entry = inbound._log(
            **base, user=user if may_send(user, ml) else None, status=rejected, reason=reason
        )
        if entry.user_id:
            notify_rejected(entry, reason)
        return entry
    try:
        invitation = imip.read(text)
    except imip.NotUsable as exc:
        invitation, problem = None, str(exc)
    else:
        problem = ""
    address, own = sender_of(msg, invitation) if invitation else (base["sender"], True)
    user = inbound.user_for(address)
    if not may_send(user, ml):
        return inbound._log(
            **base, user=user, status=rejected, reason="Absender darf hier keine Termine anlegen."
        )
    if invitation is not None and invitation.method == "REPLY":
        return inbound._log(
            **base, user=user, status=rejected, reason="Antwort auf eine Einladung."
        )
    series: dict = {}
    if invitation is not None and invitation.method != "CANCEL":
        try:
            series = series_of(invitation)
        except imip.NotUsable as exc:
            problem = str(exc)
    if problem:
        entry = inbound._log(**base, user=user, status=rejected, reason=problem)
        notify_rejected(entry, problem)
        return entry
    existing = find_event(ml, invitation.uid)
    if invitation.method == "CANCEL":
        action = CANCEL
    else:
        action = UPDATE if existing is not None else NEW
    if not own:
        from core.ratelimit import too_many

        if too_many(f"imip:ext:{ml.organization_id}:{user.pk}", 10, 3600):
            return inbound._log(
                **base, user=user, status=rejected, reason="Zu viele externe Termineinladungen."
            )
    if own:
        with rls_bypass():
            older = InboundMail.objects.filter(
                mailing_list=ml,
                status=InboundMail.Status.WAITING,
                event_data__uid=invitation.uid,
            )
            for old in older:
                _drop_stash(old)
                old.status = rejected
                old.reason = "Durch eine neuere Einladung ersetzt."
                old.save(update_fields=["status", "reason"])
    if action == CANCEL and existing is None:
        reason = "Absage zu einem Termin, der nicht übernommen wurde."
        return inbound._log(**base, user=user, status=rejected, reason=reason)
    if existing is not None and invitation.sequence < existing.mail_sequence:
        reason = "Ältere Fassung einer schon übernommenen Einladung."
        return inbound._log(**base, user=user, status=rejected, reason=reason)
    if action == UPDATE and not changes(existing, invitation):
        return inbound._log(
            **base, user=user, event=existing, status=rejected, reason="Keine Änderung."
        )
    files, skipped = (
        _stash_pdfs(msg, ml.organization) if (action != CANCEL and own) else ([], [])
    )
    data = {**invitation.as_data(), "action": action, "files": files, "skipped": skipped}
    data.update(series)
    if data.get("repeat_until"):
        data["repeat_until"] = data["repeat_until"].isoformat()
    direct = ml.mode == ml.Mode.DIRECT and own and inbound.dmarc_passed(msg)
    entry = inbound._log(
        **base,
        user=user,
        event=existing,
        event_data=data,
        status=InboundMail.Status.WAITING,
    )
    if direct:
        try:
            apply(entry)
            entry.refresh_from_db()
        except serializers.ValidationError as exc:
            entry.status = rejected
            entry.reason = _message(exc)[:300]
            entry.save(update_fields=["status", "reason"])
            notify_rejected(entry, entry.reason)
        return entry
    transaction.on_commit(lambda: notify_confirm(entry))
    return entry


def _message(exc) -> str:
    detail = getattr(exc, "detail", None) or getattr(exc, "message_dict", None) or exc
    if isinstance(detail, dict):
        return " ".join(str(v[0] if isinstance(v, list) else v) for v in detail.values())
    if isinstance(detail, list):
        return " ".join(str(v) for v in detail)
    return str(detail)


def changes(event: Event, invitation: imip.Invitation) -> dict:
    """Was die Einladung am Termin ändert (Feld → neuer Wert)."""
    wanted = {
        "title": invitation.title,
        "starts_at": invitation.starts_at,
        "ends_at": invitation.ends_at,
        "all_day": invitation.all_day,
        "location": invitation.location,
        "description": invitation.description,
        "video_url": invitation.video_url or event.video_url,
    }
    return {k: v for k, v in wanted.items() if getattr(event, k) != v}


# --- Übernehmen ---


def options_for(entry) -> dict:
    """Voreinstellungen, die der Absender auf der Bestätigungsseite ändern kann."""
    ml = entry.mailing_list
    data = entry.event_data or {}
    members = visibility_for(ml) == Event.Visibility.MEMBERS
    club = ml.organization.type == "club"
    series = bool(data.get("repeat"))
    return {
        "rsvp_possible": members and club and not series and data.get("action") == NEW,
        "rsvp": bool(ml.event_rsvp and members and club and not series),
        "video_possible": data.get("action") != CANCEL
        and not data.get("video_url")
        and talk_available(ml.organization),
        "video": bool(ml.event_video),
    }


def talk_available(org) -> bool:
    try:
        from oidc import nc_talk  # Talk-Räume (T2), wo eingerichtet
    except ImportError:
        return False
    try:
        return nc_talk.client_for(org) is not None
    except Exception:  # noqa: BLE001
        logger.exception("Talk: Einrichtung nicht prüfbar")
        return False


def create_room(event: Event, user) -> str:
    """Neuer Talk-Raum für den Termin; leer, wenn das nicht geht."""
    try:
        from oidc import nc_talk
    except ImportError:
        return ""
    try:
        room = nc_talk.create(event, user)
    except Exception:  # noqa: BLE001 – Termin bleibt, nur ohne Raum
        logger.exception("Talk-Raum zum Termin %s nicht angelegt", event.pk)
        return ""
    return getattr(room, "url", "") or ""


def apply(entry, rsvp: bool | None = None, video: bool | None = None) -> Event:
    """Termin anlegen, ändern oder absagen; danach einladen und Bescheid geben."""
    from circulars.models import InboundMail

    with rls_bypass(), transaction.atomic():
        entry = (
            InboundMail.objects.select_for_update(of=("self",))
            .select_related("mailing_list", "mailing_list__pattern", "organization", "user")
            .get(pk=entry.pk)
        )
        if entry.status != InboundMail.Status.WAITING or not entry.event_data:
            raise serializers.ValidationError(gettext("Diese Einladung wurde schon bearbeitet."))
        ml = entry.mailing_list
        if ml is None or not may_send(entry.user, ml):
            raise serializers.ValidationError(
                gettext("Du darfst für diesen Verteiler keine Termine mehr anlegen.")
            )
        options = options_for(entry)
        want_rsvp = options["rsvp"] if rsvp is None else (rsvp and options["rsvp_possible"])
        want_video = options["video"] if video is None else bool(video)
        want_video = want_video and options["video_possible"]
        data = entry.event_data
        invitation = imip.Invitation.from_data(data)
        action = data["action"]
        event = find_event(ml, invitation.uid)
        if action == NEW and event is not None:
            action = UPDATE
        if action != NEW and event is None:
            raise serializers.ValidationError(gettext("Den Termin gibt es nicht mehr."))
        before = {}
        if action == NEW:
            event = Event(
                organization=ml.organization,
                department=ml.department,
                visibility=visibility_for(ml),
                created_by=entry.user,
                mail_uid=invitation.uid,
            )
            _fill(event, invitation, data)
            event.rsvp_enabled = bool(want_rsvp)
            event.rsvp_maybe = True
        elif action == UPDATE:
            found = changes(event, invitation)
            before = {k: getattr(event, k) for k in found}
            _fill(event, invitation, data)
            if {"starts_at", "ends_at", "location"} & set(found):
                event.changed_at = timezone.now()
            if event.is_cancelled:
                event.is_cancelled = False  # Einladung zu einem abgesagten Termin: wieder da
        else:
            event.is_cancelled = True
        event.mail_sequence = max(event.mail_sequence, invitation.sequence)
        event.mail_organizer = invitation.organizer
        try:
            event.full_clean(exclude=["latitude", "longitude"])
        except ValidationError as exc:
            raise serializers.ValidationError(_message(exc)) from exc
        event.save()
        _attach(event, data.get("files") or [], entry.user)
        record(
            event.organization,
            entry.user,
            "create" if action == NEW else "update",
            event,
            {"Aus dem Mailprogramm": [None, ACTIONS[action]]}
            | {k: [str(v), str(getattr(event, k))] for k, v in before.items()},
        )
        entry.event = event
        entry.status = InboundMail.Status.SENT
        entry.save(update_fields=["event", "status"])
    room = ""
    if want_video and not event.video_url:
        room = create_room(event, entry.user)
    counts, problem = invite(entry, event, action, room)
    if action != CANCEL:
        send_reply(entry, invitation)
    notify_done(entry, event, action, room, counts, problem)
    return event


def _fill(event: Event, invitation: imip.Invitation, data: dict) -> None:
    event.title = invitation.title[:200]
    event.starts_at = invitation.starts_at
    event.ends_at = invitation.ends_at
    event.all_day = invitation.all_day
    event.location = invitation.location[:200]
    event.description = invitation.description[:5000]
    if invitation.video_url:
        event.video_url = invitation.video_url
    if data.get("repeat"):
        event.repeat = data["repeat"]
        event.repeat_interval = data.get("repeat_interval") or 1
        until = data.get("repeat_until")
        event.repeat_until = datetime.date.fromisoformat(until) if until else None
        event.rsvp_enabled = False
    else:
        event.repeat = Event.Repeat.NONE


def _attach(event: Event, files: list[dict], user) -> None:
    from core.privatefiles import read_private
    from exchange.models import private_storage

    room = MAX_ATTACHMENTS - event.attachments.count()
    for item in files:
        try:
            content = read_private(item["path"])
        except OSError:
            continue
        if room > 0:
            att = EventAttachment(
                event=event,
                organization=event.organization,
                name=item["name"],
                content_type="application/pdf",
                size=len(content),
                uploaded_by=user,
            )
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", item["name"])[-80:] or "anhang.pdf"
            att.file.save(safe, ContentFile(content), save=False)
            att.save()
            room -= 1
        try:
            private_storage().delete(item["path"])
        except OSError:
            pass


def discard(entry) -> None:
    from circulars.models import InboundMail

    with rls_bypass(), transaction.atomic():
        entry = InboundMail.objects.select_for_update().get(pk=entry.pk)
        if entry.status != InboundMail.Status.WAITING:
            raise serializers.ValidationError(gettext("Diese Einladung wurde schon bearbeitet."))
        _drop_stash(entry)
        entry.status = InboundMail.Status.REJECTED
        entry.reason = "Vom Absender verworfen."
        entry.save(update_fields=["status", "reason"])


# --- Einladen ---


def event_link(event: Event) -> str:
    local = timezone.localtime(event.starts_at)
    return f"{base_url(event.organization)}/termine?termin={event.pk}&datum={local:%Y-%m-%d}"


def video_of(event: Event, room: str = "") -> str:
    if room:
        return room
    talk = getattr(event, "talk_room", None)
    url = getattr(talk, "url", "") if talk is not None else ""
    return url or event.video_url


def invite(entry, event: Event, action: str, room: str = "") -> tuple[dict | None, str]:
    """Rundschreiben nach dem Muster des Verteilers. Gibt Zahlen und ggf. Problem zurück."""
    from circulars import recipients as rcp
    from circulars import services
    from circulars.models import Circular
    from circulars.views import event_text

    ml = entry.mailing_list
    pattern = ml.pattern
    with rls_bypass():
        subject, body = event_text(event)
        if action == UPDATE:
            subject = f"Geändert: {subject}"[:200]
            body = body.replace("wir laden dich herzlich ein:", "geändert:", 1)
        elif action == CANCEL:
            subject = f"Abgesagt: {subject}"[:200]
            body = body.replace("wir laden dich herzlich ein:", "abgesagt:", 1)
        video = video_of(event, room)
        if video and action != CANCEL:
            body = body.replace("\n- Wann:", f"\n- Video: {video}\n- Wann:", 1)
        linked = event.visibility == Event.Visibility.MEMBERS and event.organization.type == "club"
        with transaction.atomic():
            circular = Circular.objects.create(
                organization=ml.organization,
                department=ml.department,
                kind=Circular.Kind.NOTICE,
                audience=pattern.audience,
                filters=dict(pattern.filters or {}),
                via_app=pattern.via_app,
                also_mail=pattern.also_mail,
                subject=subject,
                body=body,
                reply_to=entry.user.email if entry.user else "",
                event=event if linked else None,
                created_by=entry.user,
            )
            if action == NEW:
                from circulars.views import copy_event_attachments

                copy_event_attachments(event, circular)
            errors = services.problems(circular)
            count = len(rcp.select(circular).chosen) if not errors else 0
            if errors or not count:
                problem = (
                    " ".join(errors.values()) if errors else "Der Verteiler hat keine Empfänger."
                )
                from circulars.inbound import delete_circular

                delete_circular(circular)
                return None, problem
            counts = services.start_sending(circular, entry.user)
    return counts, ""


def send_reply(entry, invitation: imip.Invitation) -> None:
    """„Angenommen“ an den Organisator, damit sein Kalender es zeigt (M3)."""
    from circulars import inbound

    ml = entry.mailing_list
    if not invitation.organizer or ml is None:
        return
    attendee = entry.recipient or inbound.address_of(ml)
    if not attendee or attendee == invitation.organizer:
        return
    ics = imip.reply(invitation, attendee, ml.name)
    mail.send(
        invitation.organizer,
        f"Angenommen: {invitation.title}"[:300],
        f"{ml.name} ({attendee}) hat die Einladung „{invitation.title}“ angenommen.\n",
        organization=ml.organization,
        kind="verteiler",
        calendar=(ics, "REPLY"),
        reply_to=[attendee],
        from_name=ml.name,
        fail_silently=True,
        headers={"Auto-Submitted": "auto-replied"},
    )


# --- Bescheide an den Absender ---


def confirm_url(entry) -> str:
    from circulars import inbound

    return inbound.confirm_url(entry)


def summary(entry) -> str:
    data = entry.event_data or {}
    start = timezone.localtime(datetime.datetime.fromisoformat(data["starts_at"]))
    if data.get("all_day"):
        when = f"{start:%d.%m.%Y}, ganztägig"
    else:
        when = f"{start:%d.%m.%Y}, {start:%H:%M} Uhr"
    lines = [f"Termin: {data.get('title', '')}", f"Wann: {when}"]
    if data.get("location"):
        lines.append(f"Wo: {data['location']}")
    if data.get("video_url"):
        lines.append(f"Video: {data['video_url']}")
    if data.get("repeat"):
        lines.append("Wiederholung: ja")
    return "\n".join(lines)


def _send(entry, subject: str, body: str) -> None:
    address = getattr(entry.user, "email", "")
    if not address:
        return
    mail.send(
        address,
        subject[:300],
        body,
        organization=entry.organization,
        kind="verteiler",
        fail_silently=True,
        headers={"Auto-Submitted": "auto-replied"},
    )


def _skipped(entry) -> str:
    skipped = (entry.event_data or {}).get("skipped") or []
    return ("\n\nNicht übernommene Anhänge: " + "; ".join(skipped)) if skipped else ""


def notify_confirm(entry) -> None:
    from circulars import inbound

    ml = entry.mailing_list
    action = (entry.event_data or {}).get("action", NEW)
    what = {
        NEW: "als neuer Termin",
        UPDATE: "als Änderung eines Termins",
        CANCEL: "als Absage eines Termins",
    }[action]
    body = (
        f"Hallo,\n\ndeine Einladung an den Verteiler {ml.name} ({inbound.address_of(ml)}) "
        f"liegt {what} bereit:\n\n{summary(entry)}\n\n"
        f"Erst wenn du bestätigst, übernimmt {instance_name()} ihn und informiert den "
        f"Verteiler:\n{confirm_url(entry)}\n\n"
        f"Der Link gilt {inbound.CONFIRM_DAYS} Tage. Hast du die Einladung nicht geschickt, "
        "ignoriere diese Nachricht einfach; dann passiert nichts."
        f"{_skipped(entry)}\n"
    )
    _send(entry, f"Bitte bestätigen: {entry.subject}", body)


def notify_done(entry, event: Event, action: str, room: str, counts, problem: str) -> None:
    ml = entry.mailing_list
    done = {NEW: "angelegt", UPDATE: "geändert", CANCEL: "abgesagt"}[action]
    lines = [
        "Hallo,",
        "",
        f"der Termin „{event.title}“ ist in {instance_name()} {done}.",
        f"Ansehen: {event_link(event)}",
    ]
    video = video_of(event, room)
    if video and action != CANCEL:
        lines.append(f"Videoraum: {video}")
    if counts:
        lines.append(
            f"Der Verteiler {ml.name} wird informiert ({counts.get('mail', 0)} per E-Mail"
            f"{', ' + str(counts['app']) + ' per App' if counts.get('app') else ''})."
        )
    elif problem:
        lines.append(f"Niemand wurde informiert: {problem}")
    lines += ["", "Hast du die Einladung nicht geschickt, melde dich bitte sofort beim Vorstand."]
    body = "\n".join(lines) + _skipped(entry) + "\n"
    _send(entry, f"Termin {done}: {event.title}", body)


def notify_rejected(entry, reason: str) -> None:
    body = (
        f"Hallo,\n\ndeine Einladung „{entry.subject or '(ohne Betreff)'}“ wurde nicht "
        f"übernommen:\n\n{reason}\n"
    )
    _send(entry, f"Nicht übernommen: {entry.subject or 'Termin'}", body)


# --- Antworten auf HUBIplans Einladungen (W1b) ---


def handle_reply(msg: EmailMessage, text: str | None, code: tuple[int, int], base: dict):
    """„Annehmen/Ablehnen“ aus dem Mailprogramm als Zu- oder Absage speichern."""
    from circulars import inbound
    from circulars.models import InboundMail
    from members.models import Membership

    from . import rsvp

    rejected = InboundMail.Status.REJECTED
    event_id, membership_id = code
    with rls_bypass():
        event = Event.objects.select_related("organization").filter(pk=event_id).first()
        membership = (
            Membership.objects.select_related("person", "organization")
            .filter(pk=membership_id)
            .first()
        )
    base = {**base, "mailing_list": None}
    if event is None or membership is None or membership.organization_id != event.organization_id:
        return inbound._log(**base, status=rejected, reason="Termin unbekannt.")
    base["organization"] = event.organization
    if inbound.dmarc_failed(msg):
        return inbound._log(**base, status=rejected, reason="Absender nicht echt (DMARC-Prüfung).")
    if text is None:
        return inbound._log(**base, status=rejected, reason="Antwort ohne Kalenderteil.")
    try:
        answer = imip.read(text)
    except imip.NotUsable as exc:
        return inbound._log(**base, status=rejected, reason=str(exc)[:300])
    if answer.method != "REPLY":
        return inbound._log(**base, status=rejected, reason="Keine Antwort auf eine Einladung.")
    with rls_bypass():
        address = rsvp.email_of(membership)
    sender = base["sender"]
    if not address or sender != address:
        return inbound._log(**base, status=rejected, reason="Antwort nicht vom Mitglied.")
    partstat = ""
    for attendee, state in answer.attendees:
        if attendee == address or len(answer.attendees) == 1:
            partstat = state
    status = imip.PARTSTATS.get(partstat)
    if status is None:
        return inbound._log(**base, status=rejected, reason="Antwort ohne Zu- oder Absage.")
    with rls_bypass(), transaction.atomic():
        event = Event.objects.select_for_update().get(pk=event.pk)
        allowed, reason = rsvp.member_can_respond(event)
        if allowed and not rsvp.is_invited(event, membership.pk):
            allowed, reason = False, "Nicht eingeladen."
        if not allowed:
            return inbound._log(
                **base, event=event, status=rejected, reason=(reason or "Keine Rückmeldung.")
            )
        if status == EventResponse.Status.MAYBE and not event.rsvp_maybe:
            status = EventResponse.Status.YES
        try:
            response, before = rsvp.save_response(
                event,
                membership,
                status=status,
                guests=0,
                note=None,
                source=EventResponse.Source.MAIL,
                user=None,
            )
        except serializers.ValidationError as exc:
            return inbound._log(**base, event=event, status=rejected, reason=_message(exc)[:300])
        record(
            event.organization,
            None,
            "update",
            event,
            {
                f"Rückmeldung {membership.person} (Mailprogramm)": [
                    rsvp.response_label(EventResponse(**before)) if before else None,
                    rsvp.response_label(response),
                ]
            },
        )
        return inbound._log(**base, event=event, status=InboundMail.Status.SENT)


# --- Kalenderteil in HUBIplans Einladungen (W1b) ---


def calendar_for(event: Event, membership_id: int | None, address: str, name: str):
    """``(ics, Methode)`` für die Mail an dieses Mitglied oder ``None``.

    Nur bei Terminen mit Zu- und Absage, wenn Antworten ankommen können, nicht für den
    Organisator einer Einladung aus dem Mailprogramm und nicht für Mitglieder mit eigenem
    Kalender-Abo (der Termin stünde sonst doppelt in ihrem Kalender)."""
    from urllib.parse import urlparse

    from . import rsvp_link

    if membership_id is None or not address or event.is_series:
        return None
    if not event.rsvp_enabled or event.organization.type != "club":
        return None
    if not event.is_cancelled and not rsvp_link.offers_link(event):
        return None
    if event.mail_organizer and address.lower() == event.mail_organizer.lower():
        return None
    organizer = imip.reply_address(event.pk, membership_id)
    if not organizer:
        return None
    if _has_feed(membership_id):
        return None
    host = urlparse(base_url(event.organization)).hostname or "hubiplan"
    original = event.starts_at.astimezone(datetime.UTC)
    uid = f"{event.pk}-{original:%Y%m%dT%H%M%SZ}@{host}"
    ics = imip.invitation(event, uid, address, name, organizer)
    return ics, ("CANCEL" if event.is_cancelled else "REQUEST")


def _has_feed(membership_id: int) -> bool:
    from portal.models import PortalAccess

    from .models import PersonalCalendar

    with rls_bypass():
        accesses = PortalAccess.objects.filter(membership_id=membership_id).values("pk")
        return PersonalCalendar.objects.filter(
            access_id__in=accesses, key_hash__isnull=False
        ).exists()
