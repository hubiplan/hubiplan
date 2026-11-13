"""Einfache Begrenzung von Aufrufen (z. B. Anmeldelinks, Foto-Uploads).

Der Zähler steigt atomar im Cache (Redis: INCR), damit parallele Anfragen nicht
denselben alten Stand lesen.
"""

from __future__ import annotations

import ipaddress
import socket
import threading
import time

from django.conf import settings
from django.core.cache import cache

# Namensauflösung der vertrauten Container: so lange gilt ein Ergebnis; nach einem Treffer
# daneben (z. B. neue Adresse nach dem Ausrollen) wird frühestens nach RETRY neu gefragt.
_RESOLVE_SECONDS = 60
_RETRY_SECONDS = 2
_resolved: dict[tuple[str, ...], tuple[float, float, frozenset[str]]] = {}
_resolve_lock = threading.Lock()


def _lookup(names: tuple[str, ...]) -> frozenset[str]:
    found: set[str] = set()
    for name in names:
        try:
            found.add(str(ipaddress.ip_address(name)))
            continue
        except ValueError:
            pass
        try:
            found.update(info[4][0] for info in socket.getaddrinfo(name, None))
        except OSError:
            continue
    return frozenset(found)


def _addresses(names, remote: str) -> frozenset[str]:
    """Adressen der Container mit diesen Namen im Docker-Netz (kurz gemerkt)."""
    key = tuple(names)
    now = time.monotonic()
    hit = _resolved.get(key)
    if hit is not None:
        loaded, tried, known = hit
        if remote in known and now - loaded < _RESOLVE_SECONDS:
            return known
        if remote not in known and now - tried < _RETRY_SECONDS:
            return known
    with _resolve_lock:
        known = _lookup(key)
        if not known and hit is not None:
            known = hit[2]  # Auflösung gerade gestört: letzter Stand gilt weiter
        _resolved[key] = (now, now, known)
    return known


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def bucket(value: str) -> str:
    """Adresse, unter der gezählt wird.

    Ein gewöhnlicher IPv6-Anschluss verfügt über ein ganzes /64-Netz; zählte jede einzelne
    Adresse für sich, wäre jede Grenze je Adresse durch Wechseln umgangen (Gesamtaudit
    13.11. S-02). IPv6 zählt deshalb je /64, IPv4 (auch als ``::ffff:…``) je Adresse.
    Alles andere bleibt, wie es ist.
    """
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return value
    if ip.version == 4:
        return str(ip)
    if ip.ipv4_mapped is not None:
        return str(ip.ipv4_mapped)
    return str(ipaddress.ip_network((int(ip) >> 64 << 64, 64)).network_address)


def from_proxy(request) -> bool:
    """Kommt die Anfrage vom eigenen Proxy (Caddy)?

    Mit ``TRUSTED_PROXY_HOSTS`` (im Betrieb der Dienst „web“) zählt nur die Adresse der
    Verbindung: Auf einem geteilten Server erreichen auch Nachbardienste das Backend direkt
    im Docker-Netz und könnten sonst beliebige Kopfzeilen mitschicken (Gesamtaudit 11.11.
    S-02). Ohne die Einstellung (Entwicklung, Tests) gilt jede Anfrage als vom Proxy.
    """
    names = getattr(settings, "TRUSTED_PROXY_HOSTS", None)
    if not names:
        return True
    remote = request.META.get("REMOTE_ADDR", "")
    return remote in _addresses(names, remote)


def from_website(request) -> bool:
    """Kommt die Anfrage direkt vom Webseiten-Dienst (hubiplan-website) im Docker-Netz?"""
    names = getattr(settings, "WEBSITE_HOSTS", None)
    if not names:
        return False
    remote = request.META.get("REMOTE_ADDR", "")
    return remote in _addresses(names, remote)


def is_local(request) -> bool:
    """Anfrage aus dem eigenen Container (Docker-Gesundheitsprüfung, Ausrollen)."""
    remote = request.META.get("REMOTE_ADDR", "")
    try:
        return ipaddress.ip_address(remote).is_loopback
    except ValueError:
        return False


def client_ip(request) -> str:
    """Adresse des Aufrufers.

    Vor dem Backend steht genau ein Proxy (Caddy); er setzt X-Forwarded-For neu
    und ignoriert, was der Aufrufer selbst mitschickt. Genommen wird der letzte
    Eintrag, also der, den Caddy angehängt hat. Kommt die Anfrage nicht von Caddy
    (``from_proxy``), zählt die Adresse der Verbindung. IPv6 kommt als /64-Netz zurück
    (``bucket``).
    """
    remote = request.META.get("REMOTE_ADDR", "")
    if not from_proxy(request):
        return bucket(remote)
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    parts = [p.strip() for p in forwarded.split(",") if p.strip()]
    return bucket(parts[-1] if parts else remote)


VISITOR_HEADER = "HTTP_X_HUBIPLAN_BESUCHER"


def visitor_ip(request) -> str:
    """Adresse des Besuchers einer Vereinswebseite (nur für die öffentliche Schnittstelle).

    Der Webseiten-Dienst ruft HUBIplan im Docker-Netz direkt auf und nennt die Adresse des
    Besuchers in ``X-Hubiplan-Besucher``. Sonst zählten alle Besucher aller Webseiten als
    eine Adresse (Gesamtaudit 11.11. S-01). Die Kopfzeile gilt nur vom Webseiten-Dienst.
    """
    if from_website(request):
        visitor = request.META.get(VISITOR_HEADER, "").strip()
        if _is_ip(visitor):
            return bucket(visitor)
        return bucket(request.META.get("REMOTE_ADDR", ""))
    return client_ip(request)


def too_many(key: str, limit: int, window: int) -> bool:
    """Zählt einen Aufruf; True, wenn im Zeitfenster mehr als ``limit`` waren."""
    if cache.add(key, 1, window):
        return limit < 1
    try:
        count = cache.incr(key)
    except ValueError:  # gerade abgelaufen
        cache.add(key, 1, window)
        count = 1
    return count > limit
