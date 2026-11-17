"""Verbund: Stände ohne Sperre bauen, unter Sperre gegen den aktuellen Stand prüfen.

Gesamtaudit 15.11., PF-11: Der Abgleich baute alle 5 Minuten alle Pakete aller Kopplungen
innerhalb einer Sperre der Kopplung. Jetzt wird außerhalb gebaut; ein veralteter Bau darf nie
einen neueren Stand überschreiben, und nach einem Widerruf oder Trennen geht nichts mehr hinaus.
Erfundene Daten.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

import pytest

from peering import packets, services
from peering.models import Coupling, Message

from .test_rls import as_app_role
from .test_verbund_kopplung import VEREIN, _setup, couple, net, world  # noqa: F401

pytestmark = pytest.mark.django_db


def _out(lower):
    return Message.objects.filter(coupling=lower, direction="out").count()


def test_aenderung_wird_weiter_nachgereicht(net, world):
    lower, _upper = couple(net, world)
    world["club"].name = "Schützenverein Beispiel 1920"
    world["club"].save()
    with net.on(VEREIN):
        assert services.sync(lower) == 1
        assert services.sync(lower) == 0


def test_zwei_verschraenkte_laeufe_reihen_nur_einmal_ein(net, world, monkeypatch):
    """Lauf A baut; währenddessen baut und reiht Lauf B ein. A verwirft seinen Bau."""
    lower, _upper = couple(net, world)
    world["club"].name = "Schützenverein Beispiel 1920"
    world["club"].save()
    real_build = packets.build
    inner = {"done": False}

    def build_and_race(coupling, packet):
        data = real_build(coupling, packet)
        if not inner["done"]:
            inner["done"] = True
            assert services.sync(Coupling.objects.get(pk=lower.pk)) == 1  # Lauf B
        return data

    with net.on(VEREIN):
        before = _out(lower)
        monkeypatch.setattr(packets, "build", build_and_race)
        assert services.sync(lower) == 0  # Lauf A: veraltet, nichts doppelt
        monkeypatch.setattr(packets, "build", real_build)
        assert _out(lower) == before + 1
        assert services.sync(lower) == 0


def test_widerruf_waehrend_des_baus_verhindert_das_paket(net, world, monkeypatch):
    lower, _upper = couple(net, world)
    world["club"].name = "Schützenverein Beispiel 1920"
    world["club"].save()
    real_build = packets.build

    def build_and_revoke(coupling, packet):
        data = real_build(coupling, packet)
        Coupling.objects.filter(pk=lower.pk).update(packets={})
        return data

    with net.on(VEREIN):
        before = _out(lower)
        monkeypatch.setattr(packets, "build", build_and_revoke)
        assert services.sync(lower) == 0
        assert _out(lower) == before


def test_getrennt_waehrend_des_baus_verhindert_das_paket(net, world, monkeypatch):
    lower, _upper = couple(net, world)
    world["club"].name = "Schützenverein Beispiel 1920"
    world["club"].save()
    real_build = packets.build

    def build_and_end(coupling, packet):
        data = real_build(coupling, packet)
        Coupling.objects.filter(pk=lower.pk).update(state=Coupling.State.ENDED)
        return data

    with net.on(VEREIN):
        before = _out(lower)
        monkeypatch.setattr(packets, "build", build_and_end)
        assert services.sync(lower) == 0
        assert _out(lower) == before


def test_unter_der_anwendungsrolle_dasselbe_paket(net, world):
    """Der Job läuft mit rls_bypass unter der Rolle der Anwendung (Kontext sitzungsweit, nicht
    nur in der Transaktion). Der Bau außerhalb der Sperre liefert dasselbe wie vorher."""
    from core.tenancy import rls_bypass

    lower, _upper = couple(net, world)
    world["club"].name = "Schützenverein Beispiel 1920"
    world["club"].save()
    with net.on(VEREIN):
        coupling = Coupling.objects.get(pk=lower.pk)
        expected = {
            p.key: packets.digest(packets.build(coupling, p))
            for p in packets.sendable(coupling)
            if p.build is not None
        }
        before = _out(lower)
        with as_app_role(), rls_bypass():
            assert services.sync(Coupling.objects.get(pk=lower.pk)) == 1
        lower.refresh_from_db()
        assert _out(lower) == before + 1
        for key, digest in expected.items():
            assert lower.sent_hashes[key] == digest, key
