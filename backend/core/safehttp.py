"""HTTP-Anfragen an fremde Server ohne DNS-Rebinding (Härtung H4, V8).

Der Name wird **einmal** aufgelöst, alle Adressen werden geprüft (keine internen), und
verbunden wird genau mit der geprüften Adresse. Zertifikat und SNI gelten weiter für den
Namen. Weiterleitungen folgt ``http.client`` nie.

``timeout`` gilt je Lesevorgang, ``deadline`` für die ganze Anfrage: Ein Server, der
nur tröpfchenweise antwortet, hält sonst einen Worker beliebig lange fest
(Gesamtaudit 05.11. GA-03).
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import threading
import time
import urllib.parse
from dataclasses import dataclass

from django.utils.translation import gettext


class SafeHTTPError(Exception):
    """Nicht erreichbar, nicht erlaubt oder ungültige Antwort."""


class BlockedAddress(SafeHTTPError):
    pass


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict
    body: bytes


def resolve(host: str, port: int, *, allow_internal: bool = False) -> str:
    """Name auflösen; jede Adresse muss öffentlich sein. Liefert die erste."""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise SafeHTTPError(gettext("{host} ist nicht auflösbar.").format(host=host)) from exc
    addresses = [info[4][0] for info in infos]
    if not addresses:
        raise SafeHTTPError(gettext("{host} ist nicht auflösbar.").format(host=host))
    if not allow_internal:
        for address in addresses:
            if not is_public(address):
                raise BlockedAddress(f"{host} zeigt auf eine interne Adresse.")
    return addresses[0]


# Präfixe, hinter denen eine IPv4-Adresse steckt (NAT64 nach RFC 6052/8215)
_NAT64 = (ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("64:ff9b:1::/48"))


def is_public(address: str) -> bool:
    """Öffentlich erreichbar, auch nach Übersetzung: IPv6-Adressen, die eine IPv4-Adresse
    tragen (NAT64, 6to4, Teredo, IPv4-mapped), zählen nur, wenn diese öffentlich ist
    (Gesamtaudit 05.11. GA-13)."""
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = []
        if ip.ipv4_mapped:
            embedded.append(ip.ipv4_mapped)
        if ip.sixtofour:
            embedded.append(ip.sixtofour)
        if ip.teredo:
            embedded.append(ip.teredo[1])
        if any(ip in net for net in _NAT64):
            embedded.append(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
        if embedded:
            return all(v4.is_global for v4 in embedded)
    return ip.is_global


class _PinnedHTTPS(http.client.HTTPSConnection):
    """HTTPS zu einer festen Adresse; Zertifikat und SNI für den Namen."""

    def __init__(self, host: str, port: int, address: str, timeout: float):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._address = address

    def connect(self):
        sock = socket.create_connection((self._address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _PinnedHTTP(http.client.HTTPConnection):
    """Nur Testaufbau (http erlaubt)."""

    def __init__(self, host: str, port: int, address: str, timeout: float):
        super().__init__(host, port, timeout=timeout)
        self._address = address

    def connect(self):
        self.sock = socket.create_connection((self._address, self.port), self.timeout)


def request(
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    body: bytes | None = None,
    timeout: float = 15,
    max_body: int = 1024 * 1024,
    allow_internal: bool = False,
    allow_http: bool = False,
    deadline: float | None = None,
) -> Response:
    """``deadline``: Sekunden für die ganze Anfrage (Standard: doppelter ``timeout``,
    mindestens 30)."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in (("https", "http") if allow_http else ("https",)):
        raise SafeHTTPError(gettext("Nur https-Adressen sind erlaubt."))
    if not parts.hostname or parts.username or parts.password:
        raise SafeHTTPError(gettext("Ungültige Adresse."))
    port = parts.port or (443 if parts.scheme == "https" else 80)
    address = resolve(parts.hostname, port, allow_internal=allow_internal)
    cls = _PinnedHTTPS if parts.scheme == "https" else _PinnedHTTP
    conn = cls(parts.hostname, port, address, timeout)
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    total = deadline if deadline is not None else max(30.0, 2 * timeout)
    expired = threading.Event()

    def _abort() -> None:
        # Blockierendes Lesen abbrechen: die Verbindung von außen schließen
        expired.set()
        sock = conn.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    watchdog = threading.Timer(total, _abort)
    watchdog.daemon = True
    started = time.monotonic()
    watchdog.start()
    try:
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        data = resp.read(max_body + 1)
        if expired.is_set() or time.monotonic() - started > total:
            raise SafeHTTPError(gettext("Zeitüberschreitung."))
        return Response(resp.status, dict(resp.getheaders()), data)
    except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
        if expired.is_set():
            raise SafeHTTPError(gettext("Zeitüberschreitung.")) from exc
        raise SafeHTTPError(
            gettext("nicht erreichbar ({name2})").format(name2=exc.__class__.__name__)
        ) from exc
    finally:
        watchdog.cancel()
        conn.close()
