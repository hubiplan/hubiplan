"""Meldungen des Browsers über Verstöße gegen die Inhaltsregeln (CSP) der Oberfläche.

Die Oberfläche schickt jedem Browser Regeln mit, was sie laden und ausführen darf
(``deploy/caddy/site.caddy``). Einen Verstoß blockiert der Browser; mit ``report-uri`` und
``report-to`` meldet er ihn zusätzlich hierher. So fällt ein eingeschleustes Skript im
Echtbetrieb auf, und eigene Fehler (eine Seite lädt etwas, das die Regeln nicht erlauben)
ebenso.

Die Meldung kommt ohne Anmeldung, denn der Browser schickt sie ohne Zugangsdaten, und sie ist
nicht beglaubigt: Jeder kann eine schicken. Deshalb:

- gespeichert wird nur Regel, blockierte Herkunft (ohne Pfad) und Seite (ohne Nummern und
  Abfrage), gezählt je Tag; keine Person, keine Einheit, keine Adresse des Aufrufers,
- höchstens ``MAX_BODY`` Bytes, ``PER_HOUR`` Meldungen je Adresse und Stunde (Zähler nur im
  Zwischenspeicher) und ``MAX_ROWS`` verschiedene Einträge,
- Meldungen aus Browser-Erweiterungen werden verworfen,
- höchstens eine Alarm-Mail am Tag, und nur für blockierte Skripte.

Lesen und Löschen darf nur die Plattformverwaltung.
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import urlsplit

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.parsers import BaseParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core import alarm, ratelimit
from core.version import running_version

from .models import CspReport
from .views import IsPlatformAdmin

logger = logging.getLogger(__name__)

MAX_BODY = 16 * 1024
MAX_REPORTS = 10  # Einträge je Sendung (Reporting API bündelt)
PER_HOUR = 60
MAX_ROWS = 500
SHOWN = 300
ALARM_PAUSE = 24 * 3600
ALARM_KEY = "csp-meldung-alarm"

DIRECTIVE = re.compile(r"^[a-z][a-z-]{2,38}$")
# Keine Herkunft, sondern eine Art von Inhalt
KEYWORDS = {"inline", "eval", "self", "data", "blob", "wasm-eval", "trusted-types-policy"}
# Erweiterungen und Eigenheiten des Browsers: kein Befund der Oberfläche
NOISE_SCHEMES = (
    "chrome-extension",
    "moz-extension",
    "safari-extension",
    "safari-web-extension",
    "webkit-masked-url",
    "ms-browser-extension",
    "chrome",
    "resource",
    "about",
    "opera",
    "edge",
    "vivaldi",
)
SCRIPT_DIRECTIVES = ("script-src", "script-src-elem", "script-src-attr", "worker-src")
SEGMENT_ID = re.compile(r"^(\d+|[0-9a-f]{8}-[0-9a-f-]{27}|[A-Za-z0-9_-]{20,})$")


class _Raw(BaseParser):
    """Rohdaten bis ``MAX_BODY``; ausgewertet wird in der Ansicht."""

    def parse(self, stream, media_type=None, parser_context=None):
        return stream.read(MAX_BODY + 1)


class CspParser(_Raw):
    media_type = "application/csp-report"


class ReportsParser(_Raw):
    media_type = "application/reports+json"


class JsonParser(_Raw):
    media_type = "application/json"


def _scheme(value: str) -> str:
    return value.split(":", 1)[0].lower() if ":" in value[:30] else ""


def clean_blocked(raw) -> str:
    """Blockierte Herkunft ohne Pfad und Abfrage: ``https://fremd.example`` oder ``inline``."""
    value = str(raw or "").strip()[:2000]
    if not value:
        return ""
    if value.lower() in KEYWORDS:
        return value.lower()
    scheme = _scheme(value)
    if scheme in NOISE_SCHEMES:
        return ""
    if scheme in ("data", "blob", "filesystem", "mediastream"):
        return scheme
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
    except ValueError:
        return ""
    if scheme not in ("http", "https", "ws", "wss") or not host:
        return ""
    if not re.fullmatch(r"[a-z0-9.-]{1,100}|\[[0-9a-f:]{2,45}\]", host):
        return ""
    return f"{scheme}://{host}"[:120]


def clean_page(raw) -> str:
    """Pfad der Seite ohne Abfrage; Nummern und Schlüssel im Pfad werden zu ``…``."""
    value = str(raw or "").strip()[:2000]
    try:
        path = urlsplit(value).path if "://" in value else value.split("?", 1)[0]
    except ValueError:
        return ""
    parts = []
    for segment in path.split("/")[:8]:
        if not segment:
            continue
        if SEGMENT_ID.match(segment):
            parts.append("…")
        elif re.fullmatch(r"[A-Za-z0-9._~-]{1,40}", segment):
            parts.append(segment)
        else:
            parts.append("…")
    return ("/" + "/".join(parts))[:120]


def _entries(data) -> list[dict]:
    """Beide Formate: ``{"csp-report": {…}}`` (report-uri) und die Liste der Reporting API."""
    if isinstance(data, dict) and isinstance(data.get("csp-report"), dict):
        r = data["csp-report"]
        return [
            {
                "directive": r.get("effective-directive") or r.get("violated-directive"),
                "blocked": r.get("blocked-uri"),
                "page": r.get("document-uri"),
                "source": r.get("source-file"),
            }
        ]
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    found = []
    for item in data[:MAX_REPORTS]:
        if not isinstance(item, dict) or item.get("type") != "csp-violation":
            continue
        body = item.get("body")
        if not isinstance(body, dict):
            continue
        found.append(
            {
                "directive": body.get("effectiveDirective") or body.get("violatedDirective"),
                "blocked": body.get("blockedURL"),
                "page": body.get("documentURL") or item.get("url"),
                "source": body.get("sourceFile"),
            }
        )
    return found


def clean(entry: dict) -> tuple[str, str, str] | None:
    directive = str(entry.get("directive") or "").strip().lower().split(" ")[0]
    if not DIRECTIVE.match(directive):
        return None
    source = str(entry.get("source") or "")
    if _scheme(source) in NOISE_SCHEMES:
        return None
    blocked = clean_blocked(entry.get("blocked"))
    if not blocked:
        return None
    return directive, blocked, clean_page(entry.get("page"))


def record(directive: str, blocked: str, page: str) -> bool:
    """Zählt die Meldung; True, wenn der Eintrag neu ist."""
    today = timezone.localdate()
    same = CspReport.objects.filter(directive=directive, blocked=blocked, page=page)
    if same.update(count=F("count") + 1, last_day=today):
        return False
    if CspReport.objects.count() >= MAX_ROWS:
        return False
    try:
        with transaction.atomic():
            CspReport.objects.create(
                directive=directive,
                blocked=blocked,
                page=page,
                first_day=today,
                last_day=today,
                version=running_version()[:40],
            )
    except IntegrityError:  # gleichzeitig angelegt
        same.update(count=F("count") + 1, last_day=today)
        return False
    return True


def notify(directive: str, blocked: str, page: str) -> None:
    """Alarm-Mail für ein blockiertes Skript, höchstens eine am Tag."""
    if directive not in SCRIPT_DIRECTIVES:
        return
    if not cache.add(ALARM_KEY, 1, ALARM_PAUSE):
        return
    alarm.send_alert(
        "Browser meldet ein blockiertes Skript",
        [
            f"Regel: {directive}",
            f"Blockiert: {blocked}",
            f"Seite: {page or 'unbekannt'}",
            "",
            "Der Browser hat das Skript nicht ausgeführt. Die Meldung kommt vom Browser eines",
            "Besuchers und ist nicht beglaubigt; Erweiterungen des Browsers können sie auslösen.",
            "Alle Meldungen: Plattform › Sicherheit. Weitere Mails dazu frühestens in 24 Stunden.",
        ],
    )


class CspReportView(APIView):
    """POST: Meldung des Browsers annehmen. Immer 204, damit die Antwort nichts verrät."""

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [CspParser, ReportsParser, JsonParser]

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        try:
            raw = request.data
        except Exception:  # noqa: BLE001 - unbekannte Inhaltsart, abgebrochene Sendung
            return Response(status=204)
        if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BODY:
            return Response(status=204)
        if ratelimit.too_many(f"csp-meldung:{ratelimit.client_ip(request)}", PER_HOUR, 3600):
            return Response(status=204)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, RecursionError):
            return Response(status=204)
        for entry in _entries(data):
            found = clean(entry)
            if found is None:
                continue
            try:
                if record(*found):
                    notify(*found)
            except Exception:  # noqa: BLE001 - eine Meldung darf nie einen Fehler 500 liefern
                logger.exception("CSP-Meldung konnte nicht gespeichert werden")
        return Response(status=204)


def state() -> dict:
    return {
        "total": CspReport.objects.count(),
        "limit": MAX_ROWS,
        "entries": [
            {
                "id": r.pk,
                "directive": r.directive,
                "blocked": r.blocked,
                "page": r.page,
                "count": r.count,
                "first_day": r.first_day.isoformat(),
                "last_day": r.last_day.isoformat(),
                "version": r.version,
                "script": r.directive in SCRIPT_DIRECTIVES,
            }
            for r in CspReport.objects.order_by("-last_day", "-count", "directive", "id")[:SHOWN]
        ],
    }


@extend_schema(request=None, responses=dict)
class PlatformCspReportsView(APIView):
    """GET: Meldungen (neueste zuerst). DELETE: alle entfernen."""

    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        return Response(state())

    def delete(self, request):
        CspReport.objects.all().delete()
        return Response(state())


@extend_schema(request=None, responses=dict)
class PlatformCspReportView(APIView):
    """DELETE: eine Meldung entfernen (geklärt oder ohne Belang)."""

    permission_classes = [IsPlatformAdmin]

    def delete(self, request, pk: int):
        CspReport.objects.filter(pk=pk).delete()
        return Response(state())
