"""Vorlagen für Kategorien (Konzept vereinskasse-steuern, S8); erfundene Daten."""

import pytest

from core.tenancy import tenant_context
from finance.models import Category

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture
def club(orgs):
    club = orgs["a"]
    club.enabled_modules = ["finance", "members", "tax"]
    club.save()
    return club


def test_vorlage_legt_nur_fehlende_an(api, board_a, club):
    with tenant_context(club.pk):
        Category.objects.create(organization=club, name="spenden", kind="income")
    c = api(board_a)
    url = f"/api/orgs/{club.pk}/finance/categories/templates/"
    listing = c.get(url)
    assert listing.status_code == 200, listing.content
    musik = next(t for t in listing.json() if t["key"] == "musik")
    spenden = next(x for x in musik["categories"] if x["name"] == "Spenden")
    assert spenden["exists"] is True

    resp = c.post(url, {"template": "musik"}, JSON)
    assert resp.status_code == 201, resp.content
    assert "Spenden" not in resp.json()["created"]
    with tenant_context(club.pk):
        dirigent = Category.objects.get(organization=club, name="Dirigent und Ausbilder")
        assert dirigent.artist_fees is True and dirigent.kind == "expense"
        assert Category.objects.get(organization=club, name="Zinsen").tax_area == "assets"
        assert Category.objects.get(organization=club, name="spenden").donations is False
        count = Category.objects.filter(organization=club).count()

    # Zweites Mal: nichts Neues
    again = c.post(url, {"template": "musik"}, JSON)
    assert again.status_code == 200 and again.json()["created"] == []
    with tenant_context(club.pk):
        assert Category.objects.filter(organization=club).count() == count

    assert c.post(url, {"template": "unbekannt"}, JSON).status_code == 400


def test_neutrale_vorlage_steht_vorn(api, board_a, club):
    """Ein Verein ohne Sparte (z. B. reines Kassenbuch) bekommt eine allgemeine Vorlage."""
    c = api(board_a)
    url = f"/api/orgs/{club.pk}/finance/categories/templates/"
    listing = c.get(url).json()
    assert listing[0]["key"] == "allgemein"
    names = [x["name"] for x in listing[0]["categories"]]
    assert {"Spenden", "Bankgebühren", "Miete und Nebenkosten", "Sonstiges"} <= set(names)
    resp = c.post(url, {"template": "allgemein"}, JSON)
    assert resp.status_code == 201, resp.content
    with tenant_context(club.pk):
        assert Category.objects.get(organization=club, name="Sonstiges").kind == "both"
        assert not Category.objects.filter(organization=club, name="Schießstand").exists()
