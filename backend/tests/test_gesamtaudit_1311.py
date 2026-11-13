"""Gesamtaudit 13.11.2026, Stufe 1: K-01, S-02, S-06. Alles erfunden.

S-01 und S-04 (Firmen-Meldung) stehen in test_firmen_mitarbeiter.py.
"""
# ruff: noqa: F811  (Fixtures aus test_mitgliedsantrag als Parameter)

import pytest
from django.core.cache import cache
from django.http import Http404
from django.test import RequestFactory
from rest_framework.exceptions import ValidationError

from competitions import stand_views
from core.ratelimit import bucket, client_ip, too_many, visitor_ip

from .test_mitgliedsantrag import (  # noqa: F401  (Fixtures, auch die automatische)
    club,
    leichte_aufgabe,
    submit,
)


class TestAdressenZaehlen:
    """S-02: IPv6 zählt je /64, sonst wäre jede Grenze je Adresse durch Wechseln umgangen."""

    @pytest.mark.parametrize(
        ("address", "expected"),
        [
            ("203.0.113.7", "203.0.113.7"),
            ("2001:db8:1:2:aaaa:bbbb:cccc:dddd", "2001:db8:1:2::"),
            ("2001:db8:1:2::1", "2001:db8:1:2::"),
            ("2001:db8:1:3::1", "2001:db8:1:3::"),
            ("::ffff:203.0.113.7", "203.0.113.7"),
            ("", ""),
            ("unbekannt", "unbekannt"),
        ],
    )
    def test_bucket(self, address, expected):
        assert bucket(address) == expected

    def test_anfrage(self, settings):
        settings.TRUSTED_PROXY_HOSTS = []
        settings.WEBSITE_HOSTS = []
        rf = RequestFactory()
        a = rf.get("/", REMOTE_ADDR="2001:db8:1:2::1")
        b = rf.get("/", REMOTE_ADDR="2001:db8:1:2:ffff::9")
        c = rf.get("/", REMOTE_ADDR="2001:db8:1:3::1")
        assert client_ip(a) == client_ip(b) != client_ip(c)
        assert visitor_ip(a) == visitor_ip(b) != visitor_ip(c)

    @pytest.mark.django_db
    def test_gemeinsamer_zaehler(self):
        cache.clear()
        first = bucket("2001:db8:1:2::1")
        second = bucket("2001:db8:1:2:1234::5")
        assert not too_many(f"probe:{first}", 1, 60)
        assert too_many(f"probe:{second}", 1, 60)
        assert not too_many(f"probe:{bucket('2001:db8:9::1')}", 1, 60)


@pytest.mark.django_db
class TestStandZaehler:
    """K-01: Der Zähler des Standzugangs hat ein festes Zeitfenster."""

    def test_grenze_und_festes_fenster(self, monkeypatch):
        cache.clear()
        monkeypatch.setattr(stand_views, "RATE", (3, 600))

        # Früher schrieb jeder Aufruf den Zähler mit neuer Laufzeit zurück (cache.set); im
        # Dauerbetrieb lief er nie ab. Jetzt zählt nur noch too_many (add + incr).
        def kein_set(*args, **kwargs):
            raise AssertionError("cache.set verlängert die Laufzeit des Zählers")

        monkeypatch.setattr(cache, "set", kein_set)
        view = stand_views._StandPublic()
        for _ in range(3):
            with pytest.raises(Http404):
                view.resolve("unbekannter-schluessel")
        with pytest.raises(ValidationError):
            view.resolve("unbekannter-schluessel")
        # ein anderer Zugang zählt für sich
        with pytest.raises(Http404):
            view.resolve("anderer-schluessel")


@pytest.mark.django_db(transaction=True)
class TestVolljaehrigkeit:
    """S-06: Ohne Geburtsdatum gilt niemand stillschweigend als volljährig."""

    def test_freiwilliges_geburtsdatum_leer(self, club):
        # Formular der Fixture: Geburtsdatum freiwillig
        res = submit(club["key"], birth_date=None)
        assert res.status_code == 400 and "adult" in res.json()
        res = submit(club["key"], birth_date=None, adult=True)
        assert res.status_code == 201, res.content

    def test_minderjaehrig_ohne_datum_braucht_erziehungsberechtigte(self, club):
        res = submit(club["key"], birth_date=None, adult=False, email="kind@example.org")
        assert res.status_code == 400
        assert "guardians" in res.json() or "birth_date" in res.json()
