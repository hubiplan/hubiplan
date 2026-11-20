"""Termine per CalDAV in Kalender der Nextcloud schreiben (eine Richtung: HUBIplan → Nextcloud).

Je Nextcloud-Dienst (``Client``) gibt es bis zu zwei Kalender im Dienstkonto:

- „Termine“: was jedes Mitglied der Einheit sieht (Termine der Einheit für Mitglieder und
  öffentlich, dazu die des Dachverbands nach seiner Freigabe), wie das Kalender-Abo eines
  Mitglieds ohne Untereinheit;
- „Vorstand“: die Termine „nur Vorstand“ der Einheit, wie das Vorstands-Abo.

Das Dienstkonto gibt jeden Kalender **nur lesend** an eine Gruppe der Nextcloud frei
(Voreinstellung „Mitglieder“ bzw. „Vorstand“, die Gruppen der Anmeldung über HUBIplan). In der
Nextcloud bearbeitet niemand diese Termine; geändert wird in HUBIplan, der nächste Abgleich
schreibt nach. Geschrieben wird nur, was sich geändert hat (``CalendarItem.digest``); was nicht
mehr dazugehört, wird gelöscht. Jeder Termin einer Serie ist ein eigener Eintrag, wie im Abo.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import logging
from urllib.parse import quote, urlsplit
from xml.sax.saxutils import escape

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext

from accounts.mfa import decrypt
from core import safehttp
from core.tenancy import rls_bypass

from .models import CalendarItem, Client

log = logging.getLogger(__name__)

TIMEOUT = 15
# Gleiches Fenster wie die Kalender-Abos (events.views.FEED_DAYS_BACK/AHEAD)
DAYS_BACK = 30
DAYS_AHEAD = 400
# Feste Zeitmarke: gleicher Termin ergibt gleiche Bytes und damit gleiche Prüfsumme
STAMP = "20260101T000000Z"

Kind = CalendarItem.Kind


class CalendarError(Exception):
    """Die Nextcloud hat den Auftrag nicht angenommen (Text für die Oberfläche)."""


def calendar_uri(client: Client, kind: str) -> str:
    return f"hubiplan-{client.pk}-{'vorstand' if kind == Kind.BOARD else 'termine'}"


def display_name(client: Client, kind: str) -> str:
    """Name des Kalenders in der Nextcloud, in der Vereinssprache."""
    from core.i18n import language_of_org

    name = client.organization.name
    with language_of_org(client.organization):
        if kind == Kind.BOARD:
            return gettext("{name} – Vorstand").format(name=name)
        return gettext("{name} – Termine").format(name=name)


def wanted_kinds(client: Client) -> list[str]:
    kinds = []
    if client.is_active and client.calendar_members:
        kinds.append(Kind.MEMBERS)
    if client.is_active and client.calendar_board:
        kinds.append(Kind.BOARD)
    return kinds


def group_of(client: Client, kind: str) -> str:
    group = client.calendar_board_group if kind == Kind.BOARD else client.calendar_members_group
    return " ".join((group or "").split())


# --- CalDAV ---


def _collection(client: Client, kind: str) -> str:
    base = client.base_url.rstrip("/")
    user = quote(client.service_user, safe="")
    return f"{base}/remote.php/dav/calendars/{user}/{calendar_uri(client, kind)}/"


def _dav(
    client: Client, method: str, url: str, body: bytes | None = None, content_type: str = ""
) -> int:
    if not client.service_user or not client.service_password:
        raise CalendarError(gettext("Dienstkonto und App-Passwort fehlen."))
    auth = f"{client.service_user}:{decrypt(client.service_password, purpose='nextcloud')}"
    headers = {"Authorization": "Basic " + base64.b64encode(auth.encode()).decode()}
    if content_type:
        headers["Content-Type"] = content_type
    headers["Content-Length"] = str(len(body or b""))
    try:
        resp = safehttp.request(
            method, url, headers=headers, body=body or b"", timeout=TIMEOUT, max_body=256 * 1024
        )
    except safehttp.SafeHTTPError as exc:
        raise CalendarError(str(exc)) from exc
    if resp.status == 401:
        raise CalendarError(gettext("Die Nextcloud lehnt Dienstkonto oder App-Passwort ab."))
    return resp.status


def _fail(status: int) -> CalendarError:
    return CalendarError(
        gettext("Die Nextcloud antwortet mit Fehler {status}.").format(status=status)
    )


def ensure_calendar(client: Client, kind: str) -> bool:
    """Kalender anlegen, falls es ihn nicht gibt; ``True``, wenn er neu ist."""
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<c:mkcalendar xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
        f"<d:set><d:prop><d:displayname>{escape(display_name(client, kind))}</d:displayname>"
        '<c:supported-calendar-component-set><c:comp name="VEVENT"/>'
        "</c:supported-calendar-component-set></d:prop></d:set></c:mkcalendar>"
    ).encode()
    status = _dav(client, "MKCALENDAR", _collection(client, kind), body, "application/xml")
    if status == 201:
        return True
    if status == 405:  # gibt es schon
        return False
    raise _fail(status)


def _share_body(group: str, remove: bool = False) -> bytes:
    href = f"principal:principals/groups/{escape(quote(group, safe=''))}"
    inner = (
        f"<o:remove><d:href>{href}</d:href></o:remove>"
        if remove
        else f"<o:set><d:href>{href}</d:href></o:set>"  # ohne <o:read-write/>: nur lesen
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<o:share xmlns:d="DAV:" xmlns:o="http://owncloud.org/ns">{inner}</o:share>'
    ).encode()


def share(client: Client, kind: str, group: str, remove: bool = False) -> None:
    """Kalender nur lesend für eine Gruppe freigeben (oder die Freigabe zurücknehmen)."""
    if not group:
        return
    status = _dav(
        client, "POST", _collection(client, kind), _share_body(group, remove), "application/xml"
    )
    if status not in (200, 204):
        if not remove:
            raise CalendarError(
                gettext("Freigabe für die Gruppe „{group}“ ging nicht (Fehler {status}).").format(
                    group=group, status=status
                )
            )


def delete_calendar(client: Client, kind: str) -> None:
    status = _dav(client, "DELETE", _collection(client, kind))
    if status not in (200, 204, 404):
        raise _fail(status)


# --- Inhalt ---


def _host() -> str:
    from .provider import issuer

    return urlsplit(issuer()).hostname or "hubiplan"


def occurrences_for(client: Client, kind: str) -> list:
    """Die Termine eines Kalenders im Fenster des Abos (unter ``rls_bypass``)."""
    from events import services
    from events.models import Event
    from events.recurrence import occurrences

    org = client.organization
    if not org.is_active or not services.module_on(org):
        return []
    now = timezone.now()
    start = now - datetime.timedelta(days=DAYS_BACK)
    end = now + datetime.timedelta(days=DAYS_AHEAD)
    if kind == Kind.BOARD:
        events = Event.objects.filter(
            organization=org,
            department__isnull=True,
            visibility=Event.Visibility.BOARD,
            source_stale=False,
        ).select_related("organization", "department", "category")
    else:
        events = services.member_viewer(org, []).events()
    return occurrences(events, start, end)


def resource_name(kind: str, occ_key: str) -> str:
    return "hp-" + hashlib.sha256(f"{kind}:{occ_key}".encode()).hexdigest()[:32] + ".ics"


def render(occ, host: str) -> bytes:
    from events import ical

    return ical.calendar(occ.event.title, [occ], host, caldav=True, stamp=STAMP)


# --- Abgleich ---


def sync_kind(client: Client, kind: str) -> dict:
    """Einen Kalender abgleichen; liefert gezählte Änderungen."""
    created = ensure_calendar(client, kind)
    items = {i.name: i for i in CalendarItem.objects.filter(client=client, kind=kind)}
    if created and items:
        # Kalender war in der Nextcloud gelöscht: alles neu schreiben
        CalendarItem.objects.filter(client=client, kind=kind).delete()
        items = {}
    share(client, kind, group_of(client, kind))
    host = _host()
    base = _collection(client, kind)
    seen: set[str] = set()
    counts = {"written": 0, "deleted": 0, "unchanged": 0}
    for occ in occurrences_for(client, kind):
        name = resource_name(kind, occ.key)
        if name in seen:
            continue
        seen.add(name)
        body = render(occ, host)
        digest = hashlib.sha256(body).hexdigest()
        item = items.get(name)
        if item is not None and item.digest == digest:
            counts["unchanged"] += 1
            continue
        status = _dav(client, "PUT", base + name, body, "text/calendar; charset=utf-8")
        if status not in (200, 201, 204):
            raise _fail(status)
        if item is None:
            CalendarItem.objects.create(
                organization=client.organization,
                client=client,
                kind=kind,
                name=name,
                digest=digest,
            )
        else:
            item.digest = digest
            item.save(update_fields=["digest", "written_at"])
        counts["written"] += 1
    for name, item in items.items():
        if name in seen:
            continue
        status = _dav(client, "DELETE", base + name)
        if status not in (200, 204, 404):
            raise _fail(status)
        item.delete()
        counts["deleted"] += 1
    return counts


def sync(client: Client, unshare: dict | None = None) -> dict:
    """Beide Kalender eines Dienstes abgleichen; abgeschaltete werden in der Nextcloud gelöscht.

    ``unshare``: {Art: Gruppe} früherer Freigaben, die zurückgenommen werden sollen."""
    result: dict = {}
    errors: list[str] = []
    wanted = wanted_kinds(client)
    for kind, group in (unshare or {}).items():
        if kind in wanted and group and group != group_of(client, kind):
            try:
                share(client, kind, group, remove=True)
            except CalendarError as exc:
                errors.append(str(exc))
    for kind in (Kind.MEMBERS, Kind.BOARD):
        try:
            if kind in wanted:
                result[kind] = sync_kind(client, kind)
            elif CalendarItem.objects.filter(client=client, kind=kind).exists():
                delete_calendar(client, kind)
                CalendarItem.objects.filter(client=client, kind=kind).delete()
                result[kind] = {"removed": True}
        except CalendarError as exc:
            errors.append(str(exc))
        except Exception:  # noqa: BLE001 – der andere Kalender soll trotzdem laufen
            log.exception("Nextcloud-Kalender %s/%s nicht abgeglichen", client.pk, kind)
            errors.append(gettext("Unerwarteter Fehler beim Abgleich."))
    client.calendar_error = "; ".join(errors)[:500]
    client.calendar_synced_at = timezone.now()
    client.save(update_fields=["calendar_error", "calendar_synced_at"])
    result["error"] = client.calendar_error
    return result


def sync_client(client_id: int, unshare: dict | None = None) -> dict:
    with rls_bypass():
        client = Client.objects.select_related("organization").filter(pk=client_id).first()
        if client is None:
            return {}
        return sync(client, unshare)


def sync_all() -> int:
    """Alle Dienste mit eingeschaltetem Kalender (und solche mit Resten zum Aufräumen)."""
    with rls_bypass():
        on = Client.objects.filter(Q(calendar_members=True) | Q(calendar_board=True))
        ids = set(on.values_list("pk", flat=True))
        ids |= set(CalendarItem.objects.values_list("client_id", flat=True).distinct())
    for pk in sorted(ids):
        sync_client(pk)
    return len(ids)
