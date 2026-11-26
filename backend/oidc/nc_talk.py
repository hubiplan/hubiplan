"""Videoraum am Termin über Nextcloud Talk (nur über das Dienstkonto).

Auf Knopfdruck am Termin legt HUBIplan im Dienstkonto ein öffentliches Talk-Gespräch mit
Passwort an. Link und Passwort sehen alle, die den Termin in HUBIplan sehen (Verwaltung,
Mitgliederbereich, Apps), dazu Einladungsmail und Kalender der Nextcloud; die öffentliche
Webseite und die Kalender-Abos tragen sie nie. ``talk_keep_days`` Tage nach dem Termin (bei
Serien nach ``repeat_until``) löscht HUBIplan das Gespräch samt Chat in der Nextcloud.
"""

from __future__ import annotations

import datetime
import logging
import secrets
import string

from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
from django.utils.translation import gettext

from accounts.mfa import decrypt, encrypt
from audit.log import record
from core.tenancy import rls_bypass

from .models import Client, TalkRoom
from .nc_files import FilesError, _ocs

log = logging.getLogger(__name__)

API = "apps/spreed/api/v4/room"


class TalkError(FilesError):
    pass


def client_for(organization) -> Client | None:
    """Eingeschalteter Nextcloud-Eintrag mit Talk für die Einheit (der erste)."""
    with rls_bypass():
        return (
            Client.objects.filter(organization=organization, talk_enabled=True, is_active=True)
            .exclude(service_user="")
            .exclude(service_password="")
            .order_by("pk")
            .first()
        )


def new_password() -> str:
    """Passwort, das auch strenge Passwortregeln der Nextcloud erfüllt (Groß, klein, Ziffer,
    Sonderzeichen, 16 Zeichen)."""
    pools = [string.ascii_uppercase, string.ascii_lowercase, string.digits, "-_+"]
    alphabet = "".join(pools).replace("l", "").replace("I", "").replace("O", "").replace("0", "")
    chars = [secrets.choice(p) for p in pools]
    chars += [secrets.choice(alphabet) for _ in range(12)]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def room_name(event) -> str:
    start = timezone.localtime(event.starts_at)
    return f"{event.title[:200]} ({start:%d.%m.%Y})"


def ends_on(event) -> datetime.datetime | None:
    """Wann der Termin vorbei ist (Serie: Ende der Wiederholung; offene Serie: nie)."""
    if event.repeat != "none":
        if not event.repeat_until:
            return None
        day = event.repeat_until + datetime.timedelta(days=1)
        return timezone.make_aware(datetime.datetime.combine(day, datetime.time()))
    return event.ends_at


def password_of(room: TalkRoom) -> str:
    if not room.password:
        return ""
    try:
        return decrypt(room.password, purpose="nextcloud")
    except ImproperlyConfigured:  # Schlüssel fehlt: Link bleibt nutzbar, Passwort nicht
        return ""


def room_data(room: TalkRoom | None) -> dict | None:
    if room is None:
        return None
    return {
        "url": room.url,
        "password": password_of(room),
        "created_at": room.created_at,
        "talk": True,
    }


def link_data(event) -> dict | None:
    """Fremder Videolink am Termin (aus einer Einladung oder von Hand), wenn kein Raum da ist."""
    url = getattr(event, "video_url", "") or ""
    if not url:
        return None
    return {"url": url, "password": "", "created_at": None, "talk": False}


def video_of(event) -> dict | None:
    """Videoraum von HUBIplan, sonst der fremde Videolink des Termins."""
    return room_data(room_of(event)) or link_data(event)


def room_of(event) -> TalkRoom | None:
    """Raum des Termins; wer den Termin sieht, sieht ihn (auch aus einer anderen Einheit)."""
    if not event.pk:
        return None
    with rls_bypass():
        return TalkRoom.objects.select_related("client").filter(event_id=event.pk).first()


def rooms_for(occurrences) -> dict[int, dict]:
    """Videoräume (sonst fremde Videolinks) der Termine einer Liste (eine Abfrage)."""
    events = {o.event.pk: o.event for o in occurrences}
    if not events:
        return {}
    out = {pk: link for pk, e in events.items() if (link := link_data(e))}
    with rls_bypass():
        rooms = TalkRoom.objects.select_related("client").filter(event_id__in=events)
        out.update({r.event_id: room_data(r) for r in rooms})
    return out


def create(event, user) -> TalkRoom:
    """Videoraum zum Termin anlegen (gibt es schon einen, bleibt er)."""
    existing = room_of(event)
    if existing is not None:
        return existing
    client = client_for(event.organization)
    if client is None:
        raise TalkError(
            gettext("Für diese Einheit ist kein Videoraum in der Nextcloud eingerichtet.")
        )
    try:
        data = _ocs(client, "POST", API, {"roomType": 3, "roomName": room_name(event)})
    except FilesError as exc:
        raise TalkError(
            gettext("Talk in der Nextcloud antwortet nicht wie erwartet ({error}).").format(
                error=exc
            )
        ) from exc
    token = str((data or {}).get("token") or "")
    if not token or not token.isalnum() or len(token) > 64:
        raise TalkError(gettext("Talk in der Nextcloud hat keinen Raum angelegt."))
    password = new_password()
    try:
        _ocs(client, "PUT", f"{API}/{token}/password", body_params={"password": password})
        _ocs(
            client,
            "PUT",
            f"{API}/{token}/description",
            {"description": gettext("Videoraum aus HUBIplan, wird nach dem Termin gelöscht.")},
        )
    except FilesError as exc:
        _remove(client, token)
        raise TalkError(
            gettext("Der Videoraum ließ sich nicht mit Passwort schützen ({error}).").format(
                error=exc
            )
        ) from exc
    with rls_bypass():
        room = TalkRoom.objects.create(
            organization=event.organization,
            client=client,
            event=event,
            token=token,
            password=encrypt(password, purpose="nextcloud"),
            created_by=user,
        )
        record(event.organization, user, "create", room)
    return room


def _remove(client: Client, token: str) -> bool:
    try:
        _ocs(client, "DELETE", f"{API}/{token}")
    except FilesError as exc:
        if getattr(exc, "status", None) == 404:
            return True
        log.warning("Talk-Raum %s ließ sich nicht löschen: %s", token, exc)
        return False
    return True


def delete(room: TalkRoom, user=None) -> bool:
    """Gespräch in der Nextcloud und den Eintrag löschen (bleibt bei Fehlern für später)."""
    if not _remove(room.client, room.token):
        return False
    with rls_bypass():
        record(room.organization, user, "delete", room)
        room.delete()
    return True


def due(now: datetime.datetime | None = None) -> list[TalkRoom]:
    now = now or timezone.now()
    out = []
    with rls_bypass():
        rooms = list(TalkRoom.objects.select_related("client", "event", "organization"))
    for room in rooms:
        if room.event_id is None:
            out.append(room)
            continue
        end = ends_on(room.event)
        if end is not None and end + datetime.timedelta(days=room.client.talk_keep_days) < now:
            out.append(room)
    return out


def purge_due(now: datetime.datetime | None = None) -> int:
    """Räume vergangener oder gelöschter Termine löschen."""
    done = 0
    for room in due(now):
        try:
            done += delete(room)
        except Exception:  # ein Raum darf die anderen nicht aufhalten
            log.exception("Talk-Raum %s ließ sich nicht löschen", room.pk)
    return done


def mail_lines(event) -> list[str]:
    """Zeilen für Einladung und Erinnerung."""
    video = video_of(event)
    if video is None:
        return []
    password = video["password"]
    lines = [f"Videoraum: {video['url']}"]
    if password:
        lines.append(f"Passwort für den Videoraum: {password}")
    return lines
