"""Farbrollen der Palette: Fließtext, Sekundärtext, Flächen, Hintergrund (erfundene Daten).

Ralf 13.11.2026: Die „Verwendung“ einer Farbe soll wirken. Wer bei einer Farbe „Fließtext“
ankreuzt, bekommt sie als Vorgabe in Webseite › Gestaltung und, wenn eingeschaltet, auch in
der HUBIplan-Oberfläche."""

import pytest
from django.core.exceptions import ValidationError
from django.test import Client

from organizations.models import Department
from organizations.theme import clean_palette_roles, effective_theme
from website import designs
from website.models import Website, WebsiteDomain

pytestmark = pytest.mark.django_db(transaction=True)
JSON = "application/json"

PALETTE = {
    "primary_color": "#05487a",
    "accent_color": "#032e52",
    "extra_colors": [
        {"color": "#3c3d3e", "name": "Anthrazit", "use": "Fließtext"},
        {"color": "#5c5d5e", "name": "Grau"},
        {"color": "#eef2f6", "name": "Hellblau-Grau"},
        {"color": "#ffffff", "name": "Weiß"},
    ],
    "palette_roles": {"text": 2, "muted": 3, "surface": 4, "background": 5},
    "palette_roles_in_app": True,
}


def _url(org):
    return f"/api/orgs/{org.pk}/theme/"


class TestPruefen:
    def test_gueltig(self):
        assert clean_palette_roles({"text": 2, "surface": None}) == {"text": 2}
        assert clean_palette_roles(None) == {}

    @pytest.mark.parametrize(
        "value",
        [[2], {"kopf": 2}, {"text": "2"}, {"text": True}, {"text": 6}, {"text": -1}],
    )
    def test_ungueltig(self, value):
        with pytest.raises(ValidationError):
            clean_palette_roles(value)


def test_speichern_und_effektiv(api, orgs, board_a):
    resp = api(board_a).patch(_url(orgs["a"]), PALETTE, content_type=JSON)
    assert resp.status_code == 200, resp.content
    data = resp.json()
    assert data["palette_roles"] == PALETTE["palette_roles"]
    assert data["palette_roles_in_app"] is True
    eff = data["effective"]
    assert eff["palette_roles"] == PALETTE["palette_roles"]
    assert eff["palette_roles_in_app"] is True


def test_ungueltige_rolle_abgelehnt(api, orgs, board_a):
    resp = api(board_a).patch(_url(orgs["a"]), {"palette_roles": {"kopf": 0}}, content_type=JSON)
    assert resp.status_code == 400


def test_fehlender_platz_entfaellt(orgs):
    org = orgs["a"]
    org.primary_color = "#05487a"
    org.extra_colors = [{"color": "#3c3d3e", "name": "Anthrazit"}]
    org.palette_roles = {"text": 2, "surface": 5}
    org.palette_roles_in_app = True
    org.save()
    eff = effective_theme(org.ancestors())
    assert eff["palette_roles"] == {"text": 2}


def test_ohne_rollen_nicht_in_der_oberflaeche(orgs):
    org = orgs["a"]
    org.primary_color = "#05487a"
    org.palette_roles_in_app = True
    org.save()
    assert effective_theme(org.ancestors())["palette_roles_in_app"] is False


def test_erbt_mit_der_hauptfarbe(orgs):
    org = orgs["a"]
    for k, v in PALETTE.items():
        setattr(org, k, v)
    org.save()
    dept = Department.objects.create(organization=org, parent=org, name="Jugend (erfunden)")
    eff = effective_theme(dept.ancestors())
    assert eff["palette_roles"]["surface"] == 4
    assert eff["palette_roles_in_app"] is True


class TestWebseite:
    PAL = [
        {"color": "#05487a"},
        {"color": "#032e52"},
        {"color": "#3c3d3e"},
        {"color": "#eef2f6"},
    ]

    def test_farbrolle_ist_vorgabe(self):
        colors = designs.resolve("classic", self.PAL, None, None, None, {"text": 2, "surface": 3})
        assert colors["text"]["color"] == "#3c3d3e"
        assert colors["surface"]["color"] == "#eef2f6"
        assert "background" not in colors

    def test_wahl_im_design_geht_vor(self):
        roles = {"classic": {"surface": "light"}}
        colors = designs.resolve("classic", self.PAL, roles, None, None, {"surface": 3})
        assert colors["surface"]["color"] == designs.NEUTRAL["light"]

    def test_ohne_farbrollen_wie_bisher(self):
        assert "text" not in designs.resolve("classic", self.PAL, None, None, None, {})


def test_schnittstelle_liefert_farbrollen(orgs):
    org = orgs["a"]
    for k, v in PALETTE.items():
        setattr(org, k, v)
    org.enabled_modules = [*org.enabled_modules, "website"]
    org.save()
    site = Website.objects.create(
        organization=org,
        public_key="schluessel-r",
        state=Website.State.PUBLIC,
        privacy_text="Datenschutz (erfunden)",
        privacy_published_text="Datenschutz (erfunden)",
    )
    WebsiteDomain.objects.create(organization=org, website=site, hostname="www.rollen.example")
    data = Client().get("/api/public/site/v1/schluessel-r/").json()
    classic = data["designs"]["classic"]
    assert classic["text"]["color"] == "#3c3d3e"
    assert classic["muted"]["color"] == "#5c5d5e"
    assert classic["surface"]["color"] == "#eef2f6"
    assert classic["background"]["color"] == "#ffffff"
