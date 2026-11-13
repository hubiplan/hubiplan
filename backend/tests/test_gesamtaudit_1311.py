"""Gesamtaudit 13.11.2026: K-01, S-02, S-03, S-06, S-07, V-04. Alles erfunden.

S-01 und S-04 (Firmen-Meldung) stehen in test_firmen_mitarbeiter.py.
"""
# ruff: noqa: F811  (Fixtures aus test_mitgliedsantrag als Parameter)

import datetime

import pytest
from django.core import mail
from django.core.cache import cache
from django.http import Http404
from django.test import Client, RequestFactory
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from admission import services
from admission.models import Application
from competitions import stand_views
from core.ratelimit import bucket, client_ip, too_many, visitor_ip
from core.tenancy import rls_bypass

from .test_mitgliedsantrag import (  # noqa: F401  (Fixtures, auch die automatische)
    club,
    leichte_aufgabe,
    submit,
    submit_and_confirm,
)

JSON = "application/json"


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


def _angenommen(club):
    app, token = submit_and_confirm(club)
    base = f"/api/orgs/{club['org'].pk}/admission/{app.pk}/"
    res = club["client"].post(f"{base}accept/", {"invite": False}, JSON)
    assert res.status_code == 200, res.content
    app.refresh_from_db()
    return app, token, base


@pytest.mark.django_db(transaction=True)
class TestStatusLink:
    """S-03: Nach der Entscheidung zeigt der Link nur den Stand und erlischt nach 30 Tagen."""

    def test_offen_zeigt_angaben(self, club):
        _, token = submit_and_confirm(club)
        data = Client().get(f"/api/public/join/application/{token}/").json()
        assert data["name"] == "Max Muster" and data["summary"] and data["pdf"] is True
        assert Client().get(f"/api/public/join/application/{token}/pdf/").status_code == 200

    def test_nach_annahme_nur_stand(self, club):
        app, token, _ = _angenommen(club)
        res = Client().get(f"/api/public/join/application/{token}/")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "accepted" and data["number"] == app.number
        assert data["name"] == "" and data["summary"] == [] and data["pdf"] is False
        assert "Muster" not in res.content.decode()
        assert Client().get(f"/api/public/join/application/{token}/pdf/").status_code == 404

    def test_link_erlischt(self, club):
        app, token, _ = _angenommen(club)
        with rls_bypass():
            Application.objects.filter(pk=app.pk).update(
                decided_at=timezone.now() - datetime.timedelta(days=31)
            )
        assert Client().get(f"/api/public/join/application/{token}/").status_code == 404
        assert Client().post(f"/api/public/join/application/{token}/confirm/").status_code == 404

    def test_zurueckgezogen_nur_stand(self, club):
        _, token = submit_and_confirm(club)
        res = Client().post(f"/api/public/join/application/{token}/withdraw/")
        assert res.status_code == 200
        assert res.json()["summary"] == [] and res.json()["name"] == ""


@pytest.mark.django_db(transaction=True)
class TestAufbewahrung:
    """S-03 (Fachfrage 1): Beleg als PDF bei Annahme, Angaben nach zwölf Monaten weg."""

    def test_pdf_und_angaben(self, club):
        app, _, base = _angenommen(club)
        assert app.pdf and app.purge_after is not None
        with rls_bypass():
            # vor der Frist bleibt alles
            services.purge(timezone.now() + datetime.timedelta(days=300))
            app.refresh_from_db()
            assert app.data.get("street") and app.data_purged_at is None
            services.purge(timezone.now() + datetime.timedelta(days=400))
            app.refresh_from_db()
            assert app.data == {"first_name": "Max", "last_name": "Muster"}
            assert app.guardians == [] and app.signature == {} and app.mandate == {}
            assert app.data_purged_at is not None and app.pdf
        res = club["client"].get(base)
        assert res.status_code == 200 and res.json()["data_purged"] is True
        res = club["client"].get(f"{base}pdf/")
        assert res.status_code == 200 and res.content.startswith(b"%PDF")

    def test_altbestand_ohne_frist(self, club):
        """Vor der Umstellung angenommen: zählt ab der Entscheidung, PDF entsteht dabei."""
        app, _, _ = _angenommen(club)
        with rls_bypass():
            app.pdf.delete(save=False)
            Application.objects.filter(pk=app.pk).update(
                pdf="", purge_after=None, decided_at=timezone.now() - datetime.timedelta(days=400)
            )
            services.purge()
            app.refresh_from_db()
            assert app.data_purged_at is not None and app.pdf
            assert "street" not in app.data


@pytest.mark.django_db(transaction=True)
class TestKorrektur:
    """S-07: Die Korrektur prüft wie die Eingabe im Formular."""

    def test_grenzen(self, club):
        app, _ = submit_and_confirm(club)
        base = f"/api/orgs/{club['org'].pk}/admission/{app.pk}/"
        c = club["client"]
        assert c.patch(base, {"email": "keine-adresse"}, JSON).status_code == 400
        assert c.patch(base, {"city": "x" * 101}, JSON).status_code == 400
        assert c.patch(base, {"last_name": ""}, JSON).status_code == 400
        assert c.patch(base, {"gender": "unsinn"}, JSON).status_code == 400
        res = c.patch(base, {"city": "Musterdorf", "email": "max@example.org"}, JSON)
        assert res.status_code == 200, res.content
        assert res.json()["data"]["city"] == "Musterdorf"


@pytest.mark.django_db(transaction=True)
class TestBestaetigung:
    """V-04: Der Bestätigungslink wirkt genau einmal."""

    def test_zweiter_aufruf_schickt_nichts(self, club):
        _, token = submit_and_confirm(club)
        count = len(mail.outbox)
        res = Client().post(f"/api/public/join/application/{token}/confirm/")
        assert res.status_code == 200 and res.json()["status"] != "unconfirmed"
        assert len(mail.outbox) == count
