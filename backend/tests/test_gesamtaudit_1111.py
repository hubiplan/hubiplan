"""Gesamtaudit 11.11.2026: S-01 (Besucher teilen sich eine Drosselung), S-02 (Kopfzeilen von
Nachbardiensten) und P-01 (Seite „Vorstand“ lud den ganzen Verein). Alles erfunden."""

import datetime

import pytest
from django.db import connection
from django.test import Client, RequestFactory
from django.test.utils import CaptureQueriesContext

from access.models import Role, RoleAssignment
from core import ratelimit
from website import public, public_views, services
from website.models import Website

from .factories import make_member

pytestmark = pytest.mark.django_db(transaction=True)

CADDY = "192.0.2.10"
WEBSEITE = "192.0.2.20"
NACHBAR = "192.0.2.99"


@pytest.fixture(autouse=True)
def _aufloesung_leeren():
    ratelimit._resolved.clear()
    yield
    ratelimit._resolved.clear()


@pytest.fixture
def betrieb(settings):
    """Wie auf dem Server: Caddy und der Webseiten-Dienst sind benannt."""
    settings.TRUSTED_PROXY_HOSTS = [CADDY]
    settings.WEBSITE_HOSTS = [WEBSEITE]


def anfrage(remote: str, **meta):
    return RequestFactory().get("/", REMOTE_ADDR=remote, **meta)


class TestAdresseDesAufrufers:
    def test_ohne_einstellung_wie_bisher(self):
        req = anfrage(NACHBAR, HTTP_X_FORWARDED_FOR="203.0.113.5, 198.51.100.7")
        assert ratelimit.client_ip(req) == "198.51.100.7"
        assert ratelimit.visitor_ip(req) == "198.51.100.7"

    def test_kopfzeile_gilt_nur_von_caddy(self, betrieb):
        von_caddy = anfrage(CADDY, HTTP_X_FORWARDED_FOR="198.51.100.7")
        assert ratelimit.client_ip(von_caddy) == "198.51.100.7"
        # Nachbardienst im Docker-Netz: seine Angabe zählt nicht (S-02)
        vom_nachbarn = anfrage(NACHBAR, HTTP_X_FORWARDED_FOR="198.51.100.7")
        assert ratelimit.client_ip(vom_nachbarn) == NACHBAR

    def test_besucher_nur_vom_webseiten_dienst(self, betrieb):
        kopf = {"HTTP_X_HUBIPLAN_BESUCHER": "203.0.113.44"}
        assert ratelimit.visitor_ip(anfrage(WEBSEITE, **kopf)) == "203.0.113.44"
        assert ratelimit.visitor_ip(anfrage(NACHBAR, **kopf)) == NACHBAR
        # Über Caddy (Browser ruft die Schnittstelle direkt auf) zählt, was Caddy nennt
        req = anfrage(CADDY, HTTP_X_FORWARDED_FOR="198.51.100.7", **kopf)
        assert ratelimit.visitor_ip(req) == "198.51.100.7"

    def test_unbrauchbare_besucherangabe(self, betrieb):
        for wert in ("", "keine-adresse", "203.0.113.44, 198.51.100.1"):
            req = anfrage(WEBSEITE, HTTP_X_HUBIPLAN_BESUCHER=wert)
            assert ratelimit.visitor_ip(req) == WEBSEITE

    def test_neue_adresse_nach_dem_ausrollen(self, settings, monkeypatch):
        settings.TRUSTED_PROXY_HOSTS = ["web"]
        adressen = {"web": "172.30.0.5"}
        uhr = [1000.0]

        def getaddrinfo(name, port):
            if name not in adressen:
                raise OSError("unbekannt")
            return [(None, None, None, "", (adressen[name], 0))]

        monkeypatch.setattr(ratelimit.socket, "getaddrinfo", getaddrinfo)
        monkeypatch.setattr(ratelimit.time, "monotonic", lambda: uhr[0])
        assert ratelimit.from_proxy(anfrage("172.30.0.5"))
        # Caddy bekommt beim Ausrollen eine neue Adresse: kurz darauf gilt sie
        adressen["web"] = "172.30.0.9"
        uhr[0] += ratelimit._RETRY_SECONDS + 1
        assert ratelimit.from_proxy(anfrage("172.30.0.9"))
        assert not ratelimit.from_proxy(anfrage("172.30.0.5"))
        # Namensauflösung gestört: der letzte Stand gilt weiter
        del adressen["web"]
        uhr[0] += ratelimit._RESOLVE_SECONDS + 1
        assert ratelimit.from_proxy(anfrage("172.30.0.9"))

    def test_fremde_adresse_fragt_nicht_staendig_neu(self, settings, monkeypatch):
        settings.TRUSTED_PROXY_HOSTS = ["web"]
        fragen = []

        def getaddrinfo(name, port):
            fragen.append(name)
            return [(None, None, None, "", ("172.30.0.5", 0))]

        monkeypatch.setattr(ratelimit.socket, "getaddrinfo", getaddrinfo)
        for _ in range(50):
            assert not ratelimit.from_proxy(anfrage(NACHBAR))
        assert len(fragen) == 1


@pytest.fixture
def seite(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "website"]
    org.save()
    site = Website.objects.create(organization=org, public_key="schluessel-ga", state="public")
    erika = make_member(org, "Erika", "Beispiel", email="erika@example.org")
    chair = Role.objects.create(
        organization=org, name="1. Vorsitzende", on_website=True, website_position=1
    )
    RoleAssignment.objects.create(organization=org, role=chair, person=erika.person)
    return {"org": org, "site": site, "erika": erika}


def abruf(path="", **meta):
    return Client().get(f"/api/public/site/v1/schluessel-ga/{path}", **meta)


class TestDrosselungJeBesucher:
    def test_besucher_zaehlen_einzeln(self, seite, betrieb, monkeypatch):
        """S-01: Ein Besucher am Limit sperrt die anderen nicht mehr aus."""
        monkeypatch.setattr(public_views, "READ_LIMIT", 3)
        laut = {"REMOTE_ADDR": WEBSEITE, "HTTP_X_HUBIPLAN_BESUCHER": "203.0.113.1"}
        leise = {"REMOTE_ADDR": WEBSEITE, "HTTP_X_HUBIPLAN_BESUCHER": "203.0.113.2"}
        assert [abruf(**laut).status_code for _ in range(4)] == [200, 200, 200, 429]
        assert abruf(**leise).status_code == 200

    def test_nachbar_kann_keine_besucher_erfinden(self, seite, betrieb, monkeypatch):
        """S-02: Wer nicht der Webseiten-Dienst ist, zählt mit der eigenen Adresse."""
        monkeypatch.setattr(public_views, "READ_LIMIT", 3)
        codes = [
            abruf(
                REMOTE_ADDR=NACHBAR,
                HTTP_X_HUBIPLAN_BESUCHER=f"203.0.113.{n}",
                HTTP_X_FORWARDED_FOR=f"198.51.100.{n}",
            ).status_code
            for n in range(1, 5)
        ]
        assert codes == [200, 200, 200, 429]


class TestNurVonInnen:
    def test_health_einzelheiten_nur_im_container(self, betrieb):
        innen = Client().get("/api/health/", REMOTE_ADDR="127.0.0.1")
        assert innen.json() == {"status": "ok", "database": "ok", "keys": "ok"}
        nachbar = Client().get("/api/health/", REMOTE_ADDR=NACHBAR)
        assert nachbar.status_code == 200 and nachbar.json() == {"status": "ok"}

    def test_zertifikatsfrage_nur_von_caddy(self, betrieb, settings, monkeypatch):
        from organizations import addresses

        settings.ADDRESSES_FROM_LIST = True
        monkeypatch.setattr(addresses, "listed_hosts", lambda: {"verein.example.org"})
        url = "/api/intern/tls/?domain=verein.example.org"
        assert Client().get(url, REMOTE_ADDR=CADDY).status_code == 200
        assert Client().get(url, REMOTE_ADDR=NACHBAR).status_code == 404


class TestVorstandLaedtNurGezeigtePersonen:
    def _abfragen(self) -> int:
        with CaptureQueriesContext(connection) as ctx:
            resp = abruf("board/")
        assert resp.status_code == 200
        assert resp.json()["roles"][0]["holders"][0]["name"] == "Erika Beispiel"
        return len(ctx)

    def test_abfragen_unabhaengig_von_der_mitgliederzahl(self, seite):
        """P-01: Die Zahl der Abfragen wächst nicht mit dem Verein, und es werden nur die
        Mitgliedschaften der gezeigten Personen gelesen."""
        self._abfragen()  # wärmt Zwischenspeicher
        vorher = self._abfragen()
        for n in range(30):
            make_member(seite["org"], f"Vorname{n}", f"Nachname{n}")
        assert self._abfragen() == vorher
        site = public.SiteView(Website.objects.get(pk=seite["site"].pk))
        site.board()
        assert set(site.people._by_person) == {seite["erika"].person_id}

    def test_einzeln_gefragt_einwilligungen_wie_bisher(self, seite):
        erika = seite["erika"]
        otto = make_member(seite["org"], "Otto", "Muster")
        services.set_entry(erika, "email", True, "paper", None)
        services.set_entry(otto, "name", True, "paper", None)
        site = public.SiteView(Website.objects.get(pk=seite["site"].pk))
        assert site.memberships.get(erika.person_id).pk == erika.pk
        assert site.consents.get(erika.pk, set()) == {"email"}
        # Mitgliedschaft ohne vorher geladene Person: der Widerspruch gilt trotzdem
        assert site.consents.get(otto.pk, set()) == {"name"}
        assert site.person(otto.person) is None
        assert site.memberships.get(None) is None
        assert site.consents.get(10**9, set()) == set()

    def test_bereinigte_und_fremde_mitgliedschaft(self, seite, orgs):
        """Bereinigt: Widersprüche gelten weiter, Einwilligungen nicht. Mitgliedschaften
        anderer Vereine zählen wie bisher nicht."""
        from members.models import Membership

        erika = seite["erika"]
        services.set_entry(erika, "email", True, "paper", None)
        services.set_entry(erika, "results", True, "paper", None)
        Membership.objects.filter(pk=erika.pk).update(
            purged_at=datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC)
        )
        fremd = make_member(orgs["b"], "Frieda", "Fremd")
        services.set_entry(fremd, "name", True, "paper", None)
        site = public.SiteView(Website.objects.get(pk=seite["site"].pk))
        assert site.consents.get(erika.pk, set()) == {"results"}
        assert site.consents.get(fremd.pk, set()) == set()
        assert site.memberships.get(fremd.person_id) is None

    def test_viele_einzelne_laden_alle_auf_einmal(self, seite, monkeypatch):
        monkeypatch.setattr(public._People, "ALL_AFTER", 3)
        mitglieder = [make_member(seite["org"], f"V{n}", f"N{n}") for n in range(8)]
        site = public.SiteView(Website.objects.get(pk=seite["site"].pk))
        for m in mitglieder[:3]:
            assert site.memberships.get(m.person_id).pk == m.pk
        assert not site.people._all
        assert site.memberships.get(mitglieder[3].person_id).pk == mitglieder[3].pk
        assert site.people._all
        with CaptureQueriesContext(connection) as ctx:
            for m in mitglieder:
                assert site.person(m.person)["name"]
        # Mitgliedschaften, Einwilligungen und Fotos kommen nicht noch einmal aus der Datenbank
        assert len(ctx) <= 2
