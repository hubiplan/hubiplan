"""Menü der Webseite: Links nach außen und ein Hauptpunkt als Knopf (Ralf 10.11.2026,
Konzept webseite-baukasten G0). Alle Daten erfunden."""

import pytest
from django.test import Client

from website import menu
from website.models import Website
from website.public import SiteView

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db(transaction=True)
KEY = "links-a"


@pytest.fixture
def club(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "events", "website"]
    org.save()
    return org


@pytest.fixture
def site(club):
    return Website.objects.create(organization=club, public_key=KEY, state="maintenance")


@pytest.fixture
def client_web(club, api):
    user = make_user("web-links@example.org")
    give_role(user, club, permissions=["website.manage"], name="Webseite")
    return api(user)


def put(c, club, data):
    return c.put(f"/api/orgs/{club.pk}/website/", data, "application/json")


def nav(site):
    return menu.public_nav(SiteView(Website.objects.get(pk=site.pk)))


class TestLinks:
    def test_link_mit_name_und_adresse_im_menue(self, club, site, client_web):
        resp = put(
            client_web,
            club,
            {
                "block_names": {"link:1": "Dachverband"},
                "menu_links": {"link:1": "https://www.example.org/verband"},
            },
        )
        assert resp.status_code == 200, resp.content
        entry = next(n for n in nav(site) if n["key"] == "link")
        assert entry == {
            "key": "link",
            "label": "Dachverband",
            "url": "https://www.example.org/verband",
        }

    def test_link_als_unterpunkt_in_einer_aenderung(self, club, site, client_web):
        resp = put(
            client_web,
            club,
            {
                "block_names": {"link:2": "Schützenfest"},
                "menu_links": {"link:2": "https://fest.example.org/"},
                "menu": [{"key": "events", "children": [{"key": "link:2"}]}],
            },
        )
        assert resp.status_code == 200, resp.content
        events = next(n for n in nav(site) if n["key"] == "events")
        assert events["children"][0]["url"] == "https://fest.example.org/"

    def test_ohne_name_oder_adresse_kein_link(self, club, site):
        site.block_names = {"link:1": "Nur Name"}
        site.menu_links = {"link:3": "https://example.org/"}
        site.save()
        assert not any(n["key"] == "link" for n in nav(site))

    @pytest.mark.parametrize(
        "url",
        ["javascript:alert(1)", "ftp://example.org/", "www.example.org", "https://" + "a" * 300],
    )
    def test_nur_vollstaendige_http_adressen(self, club, site, client_web, url):
        resp = put(client_web, club, {"menu_links": {"link:1": url}})
        assert resp.status_code == 400

    def test_unbekannter_schluessel_und_hoechstzahl(self, club, site, client_web):
        wrong = {"menu_links": {"page:1": "https://a.example/"}}
        assert put(client_web, club, wrong).status_code == 400
        many = {f"link:{i}": f"https://a.example/{i}" for i in range(1, 12)}
        assert put(client_web, club, {"menu_links": many}).status_code == 400

    def test_oeffentliche_schnittstelle_liefert_den_link(self, club, site):
        site.state = "public"
        site.block_names = {"link:1": "Dachverband"}
        site.menu_links = {"link:1": "https://www.example.org/"}
        site.save()
        data = Client().get(f"/api/public/site/v1/{KEY}/").json()
        assert {"key": "link", "label": "Dachverband", "url": "https://www.example.org/"} in data[
            "nav"
        ]


class TestKnopf:
    def test_hauptpunkt_als_knopf(self, club, site, client_web):
        resp = put(client_web, club, {"menu_button": "contact"})
        assert resp.status_code == 200, resp.content
        contact = next(n for n in nav(site) if n["key"] == "contact")
        assert contact["button"] is True
        assert sum(1 for n in nav(site) if n.get("button")) == 1

    def test_neuer_link_als_knopf_in_einer_aenderung(self, club, site, client_web):
        resp = put(
            client_web,
            club,
            {
                "block_names": {"link:1": "Mitglied werden"},
                "menu_links": {"link:1": "https://www.example.org/beitritt"},
                "menu_button": "link:1",
            },
        )
        assert resp.status_code == 200, resp.content
        entry = next(n for n in nav(site) if n["key"] == "link")
        assert entry["button"] is True

    def test_ueberschrift_kein_knopf(self, club, site, client_web):
        assert put(client_web, club, {"menu_button": "group:history"}).status_code == 400
        assert put(client_web, club, {"menu_button": "gibtsnicht"}).status_code == 400

    def test_unterpunkt_wird_kein_knopf(self, club, site):
        site.menu_button = "contact"
        site.menu = [{"key": "events", "children": [{"key": "contact"}]}]
        site.save()
        events = next(n for n in nav(site) if n["key"] == "events")
        assert not any(c.get("button") for c in events["children"])

    def test_leer_heisst_kein_knopf(self, club, site, client_web):
        put(client_web, club, {"menu_button": "contact"})
        assert put(client_web, club, {"menu_button": ""}).status_code == 200
        assert not any(n.get("button") for n in nav(site))
