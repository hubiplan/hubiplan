"""Gesamtaudit 05.11. GA-03: Fremdabrufe mit Gesamtfrist, Laufzeitgrenzen der Aufgaben."""

import socket
import threading
import time

import pytest

from core import safehttp


def _drip_server(stop: threading.Event) -> int:
    """Lokaler Server, der alle 0,2 s ein Byte schickt und nie fertig wird."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def run():
        conn, _ = srv.accept()
        conn.recv(4096)
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 100000\r\n\r\n")
        try:
            while not stop.is_set():
                conn.sendall(b"x")
                time.sleep(0.2)
        except OSError:
            pass
        finally:
            conn.close()
            srv.close()

    threading.Thread(target=run, daemon=True).start()
    return srv.getsockname()[1]


def test_tropfender_server_wird_nach_der_gesamtfrist_abgebrochen():
    stop = threading.Event()
    port = _drip_server(stop)
    started = time.monotonic()
    try:
        with pytest.raises(safehttp.SafeHTTPError, match="Zeitüberschreitung"):
            safehttp.request(
                "GET",
                f"http://127.0.0.1:{port}/",
                timeout=5,
                deadline=1.5,
                allow_internal=True,
                allow_http=True,
            )
    finally:
        stop.set()
    # Ohne Gesamtfrist liefe der Abruf rund 20.000 s (100.000 Bytes, je 0,2 s)
    assert time.monotonic() - started < 5


def test_aufgaben_mit_fremdabruf_haben_laufzeitgrenzen():
    from cards.tasks import sync_wallets
    from circulars.tasks import fetch_inbound
    from events.tasks import sync_external_calendars
    from oidc.tasks import sync_user
    from organizations.tasks import fetch_homepage_preview
    from website.tasks import maintain_social_feeds, sync_social_feed, sync_social_feeds

    for task in (
        sync_wallets,
        fetch_inbound,
        sync_external_calendars,
        sync_user,
        fetch_homepage_preview,
        sync_social_feed,
        sync_social_feeds,
        maintain_social_feeds,
    ):
        assert task.soft_time_limit and task.time_limit > task.soft_time_limit, task.name


def test_homepage_vorschau_hat_ein_gesamtbudget(monkeypatch):
    from organizations import homepage_preview

    seen = []

    def request(method, url, **kw):
        seen.append(kw["deadline"])
        return safehttp.Response(302, {"Location": url + "x"}, b"")

    monkeypatch.setattr(safehttp, "request", request)
    with pytest.raises(safehttp.SafeHTTPError):
        homepage_preview._get("https://homepage.example/", 1000)
    assert seen and all(0 < d <= homepage_preview.BUDGET for d in seen)
