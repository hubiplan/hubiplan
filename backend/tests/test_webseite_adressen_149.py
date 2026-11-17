"""Lesbare Adressen auf der Webseite (Webseite #149): Würden, Reihen und Wettbewerbe bekommen
eine Adresse aus dem Namen, einstellbar in HUBIplan; frühere Adressen bleiben zum Weiterleiten.
Alles erfunden."""

import datetime

import pytest
from django.test import Client

from competitions.models import Competition, Series
from core.webslug import make_slug
from honors.models import Dignity, Reign

from .factories import make_website

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def site(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "website", "honors", "competitions"]
    org.save()
    return make_website(org, public_key="schluessel-149", state="public")


def public(path=""):
    return Client().get(f"/api/public/site/v1/schluessel-149/{path}")


def test_adresse_aus_dem_namen():
    assert make_slug("Hubertuskönige", "x") == "hubertuskoenige"
    assert make_slug("Schützenkönig & Prinz", "x") == "schuetzenkoenig-prinz"
    assert make_slug("!!!", "wuerde") == "wuerde"


def test_wuerde_folgt_der_mehrzahl_und_merkt_fruehere(orgs):
    org = orgs["a"]
    d = Dignity.objects.create(organization=org, name="Hubertuskönig")
    assert d.web_slug == "hubertuskoenige"
    zweite = Dignity.objects.create(organization=org, name="Hubertuskönig", unit=None)
    assert zweite.web_slug == "hubertuskoenige-2"
    d.name = "Hubertusmajestät"
    d.name_plural = "Hubertusmajestäten"
    d.save()
    assert d.web_slug == "hubertusmajestaeten"
    assert d.web_slug_history == ["hubertuskoenige"]
    # Speichern ohne Namensänderung lässt die Adresse und braucht keine Prüfung
    d.sort_order = 5
    d.save(update_fields=["sort_order"])
    d.refresh_from_db()
    assert d.web_slug == "hubertusmajestaeten"


def test_wettbewerb_mit_jahr_und_reihe(orgs):
    org = orgs["a"]
    c = Competition.objects.create(
        organization=org, title="Königsschießen", date=datetime.date(2026, 6, 1)
    )
    assert c.web_slug == "koenigsschiessen-2026"
    c2 = Competition.objects.create(
        organization=org, title="Vereinsmeisterschaft 2026", date=datetime.date(2026, 3, 1)
    )
    assert c2.web_slug == "vereinsmeisterschaft-2026"
    # Datum als Text, wie es manche Aufrufer vor dem Speichern setzen
    c3 = Competition.objects.create(organization=org, title="Pokalschießen", date="2027-05-01")
    assert c3.web_slug == "pokalschiessen-2027"
    s = Series.objects.create(organization=org, name="Vereinsmeister")
    assert s.web_slug == "vereinsmeister"
    # „reihe“ belegt die Webseite selbst
    assert Series.objects.create(organization=org, name="Reihe").web_slug == "reihe-2"


def test_selbst_festlegen_und_zuruecksetzen(orgs, board_a, api):
    org = orgs["a"]
    org.enabled_modules = [*org.enabled_modules, "honors"]
    org.save()
    c = api(board_a)
    url = f"/api/orgs/{org.pk}/honors/dignities/"
    d = c.post(url, {"name": "Schützenkönig"}, "application/json").json()
    assert d["web_slug"] == "schuetzenkoenige" and d["web_slug_auto"] is True
    other = c.post(url, {"name": "Prinz"}, "application/json").json()
    resp = c.patch(f"{url}{d['id']}/", {"web_slug": "Könige"}, "application/json")
    assert resp.status_code == 200, resp.content
    assert resp.json()["web_slug"] == "koenige" and resp.json()["web_slug_auto"] is False
    taken = c.patch(f"{url}{other['id']}/", {"web_slug": "koenige"}, "application/json")
    assert taken.status_code == 400 and "web_slug" in taken.json()
    bad = c.patch(f"{url}{other['id']}/", {"web_slug": "!!!"}, "application/json")
    assert bad.status_code == 400
    back = c.patch(f"{url}{d['id']}/", {"web_slug": ""}, "application/json").json()
    assert back["web_slug"] == "schuetzenkoenige" and back["web_slug_auto"] is True
    assert Dignity.objects.get(pk=d["id"]).web_slug_history == ["koenige"]


def test_schnittstelle_nennt_adressen(orgs, site):
    org = orgs["a"]
    d = Dignity.objects.create(organization=org, name="Hubertuskönig")
    Reign.objects.create(organization=org, dignity=d, year=2025, name="Hans Hubertus")
    d.name_plural = "Hubertusmajestäten"
    d.save()
    data = public("honors/").json()["dignities"]
    assert data[0]["slug"] == "hubertusmajestaeten"
    assert data[0]["aliases"] == ["hubertuskoenige"]
    menu = public().json()["honors_menu"]["dignities"]
    assert menu[0]["slug"] == "hubertusmajestaeten"


def test_ergebnisse_auch_unter_lesbarer_adresse(orgs, site):
    org = orgs["a"]
    comp = Competition.objects.create(
        organization=org,
        title="Königsschießen",
        date=datetime.date(2026, 6, 1),
        status="endgueltig",
        website="abschluss",
        website_depth="alle",
    )
    listing = public("results/").json()["competitions"]
    assert listing[0]["slug"] == "koenigsschiessen-2026"
    assert public("results/koenigsschiessen-2026/").status_code == 200
    comp.title = "Kaiserschießen"
    comp.save()
    # frühere Adresse findet den Wettbewerb weiter, die Antwort nennt die neue
    data = public("results/koenigsschiessen-2026/").json()
    assert data["slug"] == "kaiserschiessen-2026"
    assert data["aliases"] == ["koenigsschiessen-2026"]
    assert public("results/gibt-es-nicht/").status_code == 404
