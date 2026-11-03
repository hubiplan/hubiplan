"""Hinweis auf ein neueres Release für Betreiber (konzepte/releases.md, E9).

Einmal am Tag fragt HUBIplan den Releases-Feed auf GitHub ab, ob es ein neueres Release gibt
als das laufende. Dabei wird nichts über die Instanz gesendet; GitHub sieht nur die
IP-Adresse des Servers. Plattformverwalter sehen dann in der Oberfläche einen Hinweis.
Abschalten mit ``HUBIPLAN_UPDATE_CHECK=0`` in der .env (docs/betrieb.md, „Updates“).

Ein Stand ohne Release-Nummer (nur Commit) bekommt keinen Hinweis; ein Stand nach einem Release
(``2026.11.0+3.0a5d21e``) zählt wie dessen Release.
"""

from __future__ import annotations

import json
import logging
import re

from celery import shared_task
from django.conf import settings
from django.core.cache import cache

from . import safehttp
from .version import running_version

log = logging.getLogger(__name__)

CACHE_KEY = "hubiplan:neuestes-release"
# Hält länger als ein Tag, damit ein einzelner Ausfall von GitHub den Hinweis nicht löscht
CACHE_SECONDS = 3 * 24 * 60 * 60
MAX_BODY = 512 * 1024
TIMEOUT = 10
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "HUBIplan-Update-Pruefung"}
RELEASE = re.compile(r"^v?(\d{4})\.(\d{1,2})\.(\d+)$")
RELEASE_PAGE = re.compile(r"^https://github\.com/[\w.-]+/[\w.-]+/releases/tag/[\w.+-]+$")


def release_tuple(text: str) -> tuple[int, int, int] | None:
    m = RELEASE.match(text or "")
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def running_release(text: str) -> tuple[int, int, int] | None:
    """Release, auf dem die laufende Fassung beruht („2026.11.0+3.0a5d21e“ → 2026.11.0)."""
    return release_tuple((text or "").split("+", 1)[0])


def parse_latest(body: bytes) -> dict | None:
    """Antwort von ``/releases/latest`` lesen; None bei Entwürfen, Vorabversionen, Unsinn."""
    try:
        data = json.loads(body)
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    tag = str(data.get("tag_name") or "")
    if release_tuple(tag) is None:
        return None
    version = tag.removeprefix("v")
    url = str(data.get("html_url") or "")
    return {"version": version, "url": url if RELEASE_PAGE.match(url) else ""}


@shared_task
def check_latest() -> str | None:
    """Neuestes Release abfragen und merken (täglich, CELERY_BEAT_SCHEDULE)."""
    if not settings.UPDATE_CHECK:
        cache.delete(CACHE_KEY)
        return None
    try:
        resp = safehttp.request(
            "GET", settings.UPDATE_CHECK_URL, headers=HEADERS, timeout=TIMEOUT, max_body=MAX_BODY
        )
    except safehttp.SafeHTTPError as exc:
        log.info("Update-Prüfung: %s", exc)
        return None
    if resp.status != 200:
        log.info("Update-Prüfung: HTTP %s", resp.status)
        return None
    latest = parse_latest(resp.body)
    if latest:
        cache.set(CACHE_KEY, latest, CACHE_SECONDS)
        return latest["version"]
    return None


def available() -> dict | None:
    """Neueres Release als das laufende, sonst None."""
    if not settings.UPDATE_CHECK:
        return None
    latest = cache.get(CACHE_KEY)
    running = running_release(running_version())
    if not latest or running is None:
        return None
    newest = release_tuple(latest.get("version", ""))
    if newest is None or newest <= running:
        return None
    return {
        "version": latest["version"],
        "url": latest.get("url", ""),
        "running": running_version(),
    }
