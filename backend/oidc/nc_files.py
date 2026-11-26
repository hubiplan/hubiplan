"""Dateien mit der Nextcloud austauschen (WebDAV und Freigaben, nur über das Dienstkonto).

- **In Nextcloud ablegen**: Berichte und Exporte, die jemand in HUBIplan herunterlädt, legt
  HUBIplan auf Knopfdruck in einen Ordner des Dienstkontos (``files_root``/„Vorstand“, „Kasse“,
  „Mitglieder“). Jeder Ordner ist **nur lesend** an eine Gruppe freigegeben, die HUBIplan pflegt
  (mit dem Gruppenabgleich sofort aktuell). Nichts wird überschrieben. Jede abgelegte Datei steht
  in ``FileItem`` mit einer Frist je Art (Entscheidung Ralf 20.11.: manches dauerhaft); danach
  löscht HUBIplan sie in den Papierkorb des Dienstkontos.
- **Aus Nextcloud übernehmen**: Ein Ordner, den der Verein dem Dienstkonto freigegeben hat
  (``files_source``), lässt sich in Hochladen-Dialogen durchblättern. HUBIplan holt die Datei und
  gibt sie an den Browser, der sie wie eine eigene Datei hochlädt (gleiche Prüfungen).

Alles läuft über ``core.safehttp`` (nur https, keine internen Adressen), mit Zeit- und
Größengrenzen. Das App-Passwort steht nie in Antworten oder Protokoll.
"""

from __future__ import annotations

import base64
import datetime
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlencode, urlsplit

from defusedxml import ElementTree as SafeET
from django.utils import timezone
from django.utils.translation import gettext

from accounts.mfa import decrypt
from audit.log import record
from core import safehttp
from core.tenancy import rls_bypass

from .models import Client, FileItem

log = logging.getLogger(__name__)

TIMEOUT = 30
# Größte Datei, die HUBIplan ablegt oder übernimmt
MAX_FILE = 50 * 1024 * 1024
FOLDERS = {
    FileItem.Target.BOARD: "Vorstand",
    FileItem.Target.FINANCE: "Kasse",
    FileItem.Target.MEMBERS: "Mitglieder",
}
# Frist je Art in Jahren (None: dauerhaft); Kassen- und Meldeunterlagen ab Ende des Kalenderjahres
RETENTION_YEARS = {
    FileItem.Category.RECORDS: None,
    FileItem.Category.STATISTICS: None,
    FileItem.Category.FINANCE: 10,
    FileItem.Category.REPORTS: 6,
    FileItem.Category.OTHER: 2,
}
# Personenbezogene Listen: Stand veraltet schnell, das Original bleibt in HUBIplan
PERSONAL_DAYS = 92
YEAR_END = {FileItem.Category.FINANCE, FileItem.Category.REPORTS}

DAV = "{DAV:}"


class FilesError(Exception):
    """Die Nextcloud hat den Auftrag nicht angenommen (Text für die Oberfläche)."""


@dataclass
class Entry:
    name: str
    path: str
    is_dir: bool
    size: int
    modified: str
    content_type: str


# --- Fristen ---


def retention_years(client: Client, category: str) -> int | None | float:
    """Frist in Jahren (None: dauerhaft); eigene Werte des Eintrags gehen vor."""
    own = (client.files_retention or {}).get(category)
    if isinstance(own, int) and not isinstance(own, bool) and 0 <= own <= 100:
        return None if own == 0 else own
    if category == FileItem.Category.PERSONAL:
        return PERSONAL_DAYS / 365
    return RETENTION_YEARS.get(category, 2)


def delete_after(client: Client, category: str, today: datetime.date) -> datetime.date | None:
    years = retention_years(client, category)
    if years is None:
        return None
    if category == FileItem.Category.PERSONAL and years == PERSONAL_DAYS / 365:
        return today + datetime.timedelta(days=PERSONAL_DAYS)
    years = int(years)
    if category in YEAR_END:
        return datetime.date(today.year + years, 12, 31)
    try:
        return today.replace(year=today.year + years)
    except ValueError:  # 29. Februar
        return today.replace(year=today.year + years, day=28)


def group_for(client: Client, target: str) -> str:
    group = {
        FileItem.Target.BOARD: client.files_board_group,
        FileItem.Target.FINANCE: client.files_finance_group,
        FileItem.Target.MEMBERS: client.files_members_group,
    }.get(target, "")
    return " ".join((group or "").split())


# --- Pfade ---


def clean_segments(path: str) -> list[str]:
    """Pfad in Teile zerlegen; ``..``, leere und versteckte Teile sind nicht erlaubt."""
    parts = [p for p in str(path or "").replace("\\", "/").split("/") if p not in ("", ".")]
    for p in parts:
        if p == ".." or p.startswith(".") or any(ord(c) < 32 for c in p):
            raise FilesError(gettext("Ungültiger Pfad."))
    return parts


def clean_filename(name: str) -> str:
    name = unicodedata.normalize("NFC", str(name or "")).replace("/", "-").replace("\\", "-")
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip().lstrip(".")
    if not name:
        raise FilesError(gettext("Bitte einen Dateinamen angeben."))
    if len(name) > 150:
        stem, dot, ext = name.rpartition(".")
        name = (stem[: 140 - len(ext)] + dot + ext) if dot and len(ext) <= 8 else name[:150]
    return name


def _user_root(client: Client) -> str:
    base = client.base_url.rstrip("/")
    return f"{base}/remote.php/dav/files/{quote(client.service_user, safe='')}/"


def _url(client: Client, segments: list[str], folder: bool = False) -> str:
    url = _user_root(client) + "/".join(quote(s, safe="") for s in segments)
    return url + "/" if folder and segments else url


# --- HTTP ---


def _auth(client: Client) -> str:
    if not client.service_user or not client.service_password:
        raise FilesError(gettext("Dienstkonto und App-Passwort fehlen."))
    secret = decrypt(client.service_password, purpose="nextcloud")
    return "Basic " + base64.b64encode(f"{client.service_user}:{secret}".encode()).decode()


def _call(
    client: Client,
    method: str,
    url: str,
    body: bytes | None = None,
    headers: dict | None = None,
    max_body: int = 1024 * 1024,
) -> safehttp.Response:
    head = {"Authorization": _auth(client), **(headers or {})}
    head["Content-Length"] = str(len(body or b""))
    try:
        resp = safehttp.request(
            method,
            url,
            headers=head,
            body=body or b"",
            timeout=TIMEOUT,
            max_body=max_body,
            deadline=300,
        )
    except safehttp.SafeHTTPError as exc:
        raise FilesError(str(exc)) from exc
    if resp.status == 401:
        raise FilesError(gettext("Die Nextcloud lehnt Dienstkonto oder App-Passwort ab."))
    return resp


def _fail(status: int) -> FilesError:
    error = FilesError(
        gettext("Die Nextcloud antwortet mit Fehler {status}.").format(status=status)
    )
    error.status = status
    return error


def _ocs(
    client: Client,
    method: str,
    path: str,
    params: dict | None = None,
    *,
    body_params: dict | None = None,
):
    query = urlencode({**(params or {}), "format": "json"})
    url = f"{client.base_url.rstrip('/')}/ocs/v2.php/{path}?{query}"
    headers = {"OCS-APIRequest": "true", "Accept": "application/json"}
    body = None
    if body_params is not None:
        body = urlencode(body_params).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    resp = _call(client, method, url, body=body, headers=headers)
    try:
        ocs = json.loads(resp.body or b"{}").get("ocs", {})
    except ValueError:
        ocs = {}
    code = ocs.get("meta", {}).get("statuscode")
    if resp.status == 200 and code in (100, 200):
        return ocs.get("data")
    raise _fail(code or resp.status)


# --- Ordner und Freigaben ---


def ensure_folder(client: Client, segments: list[str]) -> None:
    """Ordner (mit allen übergeordneten) anlegen, falls es sie nicht gibt."""
    for i in range(1, len(segments) + 1):
        status = _call(client, "MKCOL", _url(client, segments[:i], folder=True)).status
        if status not in (201, 405):
            raise _fail(status)


def ensure_share(client: Client, target: str) -> None:
    """Ordner des Ziels nur lesend an seine Gruppe freigeben; frühere Freigaben von HUBIplan an
    eine andere Gruppe zurücknehmen."""
    group = group_for(client, target)
    path = "/" + "/".join([*clean_segments(client.files_root), FOLDERS[target]])
    shares = dict(client.files_shares or {})
    old = shares.get(target) or {}
    if old.get("id") and old.get("group") != group:
        try:
            _ocs(client, "DELETE", f"apps/files_sharing/api/v1/shares/{int(old['id'])}")
        except (FilesError, ValueError):
            pass
        shares.pop(target, None)
    if group:
        existing = _ocs(client, "GET", "apps/files_sharing/api/v1/shares", {"path": path}) or []
        found = next(
            (
                s
                for s in existing
                if isinstance(s, dict)
                and int(s.get("share_type", -1)) == 1
                and s.get("share_with") == group
            ),
            None,
        )
        if found is None:
            found = _ocs(
                client,
                "POST",
                "apps/files_sharing/api/v1/shares",
                {"path": path, "shareType": 1, "shareWith": group, "permissions": 1},
            )
        elif int(found.get("permissions", 1)) != 1:
            # Nur lesen: von Hand erweiterte Rechte zurücksetzen
            _ocs(
                client,
                "PUT",
                f"apps/files_sharing/api/v1/shares/{int(found['id'])}",
                {"permissions": 1},
            )
        shares[target] = {"group": group, "id": (found or {}).get("id")}
    if shares != (client.files_shares or {}):
        client.files_shares = shares
        with rls_bypass():
            Client.objects.filter(pk=client.pk).update(files_shares=shares)


def _put_unique(client: Client, folder: list[str], filename: str, content: bytes) -> list[str]:
    """Datei ablegen, ohne etwas zu überschreiben („name (2).pdf“ usw.)."""
    stem, dot, ext = filename.rpartition(".")
    if not dot:
        stem, ext = filename, ""
    for n in range(1, 50):
        name = filename if n == 1 else f"{stem} ({n}){dot}{ext}"
        segments = [*folder, name]
        status = _call(
            client,
            "PUT",
            _url(client, segments),
            content,
            {"If-None-Match": "*", "Content-Type": "application/octet-stream"},
        ).status
        if status in (200, 201, 204):
            return segments
        if status != 412:
            raise _fail(status)
    raise FilesError(gettext("Zu viele Dateien mit diesem Namen."))


def store(
    client: Client, user, target: str, category: str, filename: str, content: bytes
) -> FileItem:
    """Eine Datei in den Ordner eines Ziels legen und vermerken."""
    if not client.files_enabled or not client.is_active:
        raise FilesError(gettext("„In Nextcloud ablegen“ ist aus."))
    if target not in FOLDERS:
        raise FilesError(gettext("Unbekanntes Ziel."))
    if category not in FileItem.Category.values:
        raise FilesError(gettext("Unbekannte Art."))
    if category == FileItem.Category.PERSONAL and target == FileItem.Target.MEMBERS:
        raise FilesError(gettext("Listen mit Personendaten nie in den Ordner „Mitglieder“."))
    if len(content) > MAX_FILE:
        raise FilesError(gettext("Die Datei ist zu groß (höchstens 50 MB)."))
    folder = [*clean_segments(client.files_root), FOLDERS[target]]
    ensure_folder(client, folder)
    ensure_share(client, target)
    segments = _put_unique(client, folder, clean_filename(filename), content)
    item = FileItem.objects.create(
        organization=client.organization,
        client=client,
        target=target,
        category=category,
        path="/".join(segments),
        size=len(content),
        created_by=user,
        delete_after=delete_after(client, category, timezone.localdate()),
    )
    record(client.organization, user, "create", item, {"Nextcloud": ["", item.path]})
    return item


def purge_due(today: datetime.date | None = None) -> int:
    """Abgelegte Dateien nach ihrer Frist löschen (in den Papierkorb des Dienstkontos)."""
    today = today or timezone.localdate()
    done = 0
    with rls_bypass():
        items = list(
            FileItem.objects.filter(delete_after__lt=today, deleted_at__isnull=True).select_related(
                "client", "organization"
            )
        )
        for item in items:
            client = item.client
            try:
                status = _call(client, "DELETE", _url(client, item.path.split("/"))).status
            except FilesError:
                log.warning("Nextcloud-Datei %s nicht gelöscht", item.pk)
                continue
            if status not in (200, 204, 404):
                continue
            item.deleted_at = timezone.now()
            item.save(update_fields=["deleted_at"])
            record(item.organization, None, "delete", item, {"Nextcloud": [item.path, ""]})
            done += 1
    return done


# --- Aus Nextcloud übernehmen ---


def source_segments(client: Client, sub: str = "") -> list[str]:
    if not client.files_source.strip():
        raise FilesError(gettext("Es ist kein Ordner zum Übernehmen eingetragen."))
    return [*clean_segments(client.files_source), *clean_segments(sub)]


PROPFIND = (
    b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop>'
    b"<d:resourcetype/><d:getcontentlength/><d:getlastmodified/><d:getcontenttype/>"
    b"</d:prop></d:propfind>"
)


def list_source(client: Client, sub: str = "") -> list[Entry]:
    """Inhalt eines Ordners unterhalb des Ordners zum Übernehmen (Ordner zuerst)."""
    base = source_segments(client)
    segments = source_segments(client, sub)
    resp = _call(
        client,
        "PROPFIND",
        _url(client, segments, folder=True),
        PROPFIND,
        {"Depth": "1", "Content-Type": "application/xml"},
        max_body=4 * 1024 * 1024,
    )
    if resp.status == 404:
        raise FilesError(gettext("Den Ordner gibt es in der Nextcloud nicht (mehr)."))
    if resp.status != 207:
        raise _fail(resp.status)
    try:
        root = SafeET.fromstring(resp.body)
    except Exception as exc:  # noqa: BLE001 – kaputte oder bösartige Antwort
        raise FilesError(gettext("Die Antwort der Nextcloud ist nicht lesbar.")) from exc
    own = urlsplit(_url(client, segments, folder=True)).path.rstrip("/")
    entries = []
    for response in root.findall(f"{DAV}response"):
        href = response.findtext(f"{DAV}href") or ""
        path = urlsplit(href).path.rstrip("/")
        if path == own or not path.startswith(own + "/"):
            continue
        name = unquote(path[len(own) + 1 :])
        if "/" in name or name.startswith("."):
            continue
        prop = response.find(f"{DAV}propstat/{DAV}prop")
        if prop is None:
            continue
        is_dir = prop.find(f"{DAV}resourcetype/{DAV}collection") is not None
        size = prop.findtext(f"{DAV}getcontentlength") or "0"
        rel = "/".join([*segments[len(base) :], name])
        entries.append(
            Entry(
                name=name,
                path=rel,
                is_dir=is_dir,
                size=int(size) if size.isdigit() else 0,
                modified=prop.findtext(f"{DAV}getlastmodified") or "",
                content_type="" if is_dir else (prop.findtext(f"{DAV}getcontenttype") or ""),
            )
        )
    entries.sort(key=lambda e: (not e.is_dir, e.name.casefold()))
    return entries


def fetch_source(client: Client, sub: str) -> tuple[str, bytes]:
    """Eine Datei aus dem Ordner zum Übernehmen holen: (Dateiname, Inhalt)."""
    segments = source_segments(client, sub)
    if len(segments) <= len(source_segments(client)):
        raise FilesError(gettext("Bitte eine Datei wählen."))
    resp = _call(client, "GET", _url(client, segments), max_body=MAX_FILE)
    if resp.status == 404:
        raise FilesError(gettext("Die Datei gibt es in der Nextcloud nicht (mehr)."))
    if resp.status != 200:
        raise _fail(resp.status)
    if len(resp.body) > MAX_FILE:
        raise FilesError(gettext("Die Datei ist zu groß (höchstens 50 MB)."))
    from core import virenscan

    virenscan.scan_bytes(resp.body, segments[-1])
    return segments[-1], resp.body
