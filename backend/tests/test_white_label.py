"""White Label W1: Erscheinungsbild der Instanz ohne Anmeldung (konzepte/white-label.md)."""

import pytest
from django.test import Client

from organizations.models import Organization

from .factories import make_org

pytestmark = pytest.mark.django_db
URL = "/api/public/platform/"


def platform() -> Organization:
    return Organization.platform()


def test_ohne_eigene_angaben_wie_bisher():
    platform()
    data = Client().get(URL).json()
    assert data == {"name": "HUBIplan", "short_name": "", "logo_url": None, "theme": None}


def test_ohne_plattform_einheit_legt_nichts_an():
    Organization.objects.filter(type=Organization.Type.PLATFORM).delete()
    data = Client().get(URL).json()
    assert data["name"] == "HUBIplan"
    assert not Organization.objects.filter(type=Organization.Type.PLATFORM).exists()


def test_instanzname_und_farben():
    p = platform()
    p.name = "Vereinsportal Musterkreis"
    p.short_name = "Musterkreis"
    p.primary_color = "#1f4e79"
    p.save()
    resp = Client().get(URL)
    assert resp.status_code == 200
    assert "max-age" in resp["Cache-Control"]
    data = resp.json()
    assert data["name"] == "Vereinsportal Musterkreis"
    assert data["short_name"] == "Musterkreis"
    # Fehlende Zweitfarbe kommt vom Standard, Schriftfarbe ist lesbar berechnet
    assert data["theme"] == {
        "primary": "#1f4e79",
        "on_primary": "#ffffff",
        "accent": "#f2b33d",
        "on_accent": "#1d2421",
    }


def test_nur_angaben_der_plattform_keine_einheiten():
    p = platform()
    make_org("Schützenverein Musterstadt", primary_color="#7a1f1f")
    data = Client().get(URL).json()
    assert data["theme"] is None
    assert data["name"] == p.name


def test_kontrastpruefung_gilt_fuer_die_plattform():
    from organizations.serializers import ThemeSerializer

    s = ThemeSerializer(platform(), data={"primary_color": "#f2f2f2"}, partial=True)
    assert not s.is_valid()
    assert "primary_color" in s.errors
