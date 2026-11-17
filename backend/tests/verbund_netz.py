"""Testaufbau mit mehreren simulierten HUBIplan-Instanzen in einer Datenbank.

Jede Instanz hat eigene Schlüssel und Adresse. Anfragen zwischen ihnen gehen
über den Django-Testclient; während eine Instanz eine Anfrage bearbeitet, gelten
ihre Schlüssel und Adresse. Alle Daten sind erfunden.

Eingehende Anfragen laufen wie im Echtbetrieb in der Rolle ``hubiplan_app``, damit die
Zeilensicherheit (RLS) dort wirklich greift.

Im Betrieb ist die Anfrage an die andere Instanz ein echter HTTP-Aufruf an einen anderen
Server. Hier läuft sie verschachtelt auf derselben Datenbankverbindung; deren Middleware
setzt am Ende den RLS-Kontext zurück. ``Net`` stellt deshalb nach jedem Aufruf Rolle und
RLS-Kontext der äußeren Anfrage wieder her (Gesamtaudit 15.11., AZ-04).
"""

from __future__ import annotations

import contextlib
import urllib.parse

from django.db import DatabaseError
from django.test import Client, override_settings

from peering import identity, transport


class Net:
    def __init__(self, tmp_path):
        self.tmp_path = tmp_path
        self.instances: dict[str, str] = {}
        self.down: set[str] = set()
        self.calls: list[tuple[str, str]] = []
        self.current: str | None = None

    def add(self, base_url: str) -> str:
        name = urllib.parse.urlsplit(base_url).hostname.replace(".", "_")
        self.instances[base_url] = str(self.tmp_path / name / "instance.json")
        return base_url

    @contextlib.contextmanager
    def on(self, base_url: str):
        previous = self.current
        self.current = base_url
        with override_settings(
            PEERING_KEY_FILE=self.instances[base_url], PEERING_BASE_URL=base_url
        ):
            try:
                yield
            finally:
                self.current = previous

    def target(self, url: str) -> tuple[str, str]:
        for base in self.instances:
            if url.startswith(base + "/"):
                return base, url[len(base) :]
        raise transport.PeerError("unbekannte Adresse")

    def send(self, url, headers, body):
        base, path = self.target(url)
        self.calls.append((self.current or "", path))
        if base in self.down:
            raise transport.PeerError("nicht erreichbar (Test)")
        with aussen_bewahren(), self.on(base), app_role():
            resp = Client().post(
                path,
                data=body,
                content_type="application/json",
                headers={k: v for k, v in headers.items() if k != "Content-Type"},
            )
        return resp.status_code, dict(resp.headers), resp.content

    def get(self, url):
        base, path = self.target(url)
        if base in self.down:
            raise transport.PeerError("nicht erreichbar (Test)")
        with aussen_bewahren(), self.on(base), app_role():
            resp = Client().get(path)
        return resp.status_code, resp.content


@contextlib.contextmanager
def app_role():
    """Anfrage in der eingeschränkten Rolle der Anwendung bearbeiten (RLS aktiv)."""
    from .app_rolle import unter_app_rolle

    with unter_app_rolle():
        yield


@contextlib.contextmanager
def aussen_bewahren():
    """Rolle und RLS-Kontext (samt Bypass) der äußeren Anfrage über einen verschachtelten
    Aufruf der anderen Instanz retten. Deren Middleware setzt am Ende ``reset_rls()``; im
    Betrieb träfe das eine andere Verbindung auf einem anderen Server."""
    from core.tenancy import _apply, get_rls

    from . import app_rolle

    zustand = get_rls()
    rolle = None
    if app_rolle.aktiv() and not app_rolle.abgebrochen():
        rolle = app_rolle.rollen()[0]
    try:
        yield
    except BaseException:
        # Die Ausnahme des Aufrufs soll sichtbar bleiben, nicht ein Folgefehler in einer
        # abgebrochenen Transaktion; deren Zurückrollen stellt die Rolle ohnehin wieder her.
        if rolle is not None:
            app_rolle.wiederherstellen(rolle)
        with contextlib.suppress(DatabaseError):
            _apply(zustand)
        raise
    if rolle is not None:
        app_rolle.wiederherstellen(rolle)
    _apply(zustand)


def install(monkeypatch, tmp_path) -> Net:
    net = Net(tmp_path)
    monkeypatch.setattr(transport, "_send", net.send)
    monkeypatch.setattr(transport, "_get", net.get)
    identity.reset_cache()
    return net


def release(coupling, levels: dict):
    """Freigeben wie ``services.set_packets``; die Gegenseite hat der Stufe schon zugestimmt.

    Seit Härtung H4 nimmt die Empfängerin nur an, was sie bestätigt hat."""
    from peering import services
    from peering.models import Coupling

    other = (
        Coupling.objects.exclude(pk=coupling.pk)
        .exclude(state__in=[Coupling.State.ENDED, Coupling.State.MOVED])
        .get(local_unit__uuid=coupling.remote_uuid, remote_uuid=coupling.local_unit.uuid)
    )
    services.set_accept(other, {**services.accepted(other), **levels}, None)
    return services.set_packets(coupling, levels, None)
