"""Verwendung je Farbe, Verläufe und Rollen für Text, Flächen und Hintergrund (erfunden).

Ralf 10.11.2026: Farbblatt eines Vereins (Leitfarbe Blau, Grautöne, Blau- und Grauverlauf)
in HUBIplan abbilden."""

import pytest
from django.test import Client

from organizations.models import Department
from organizations.theme import effective_theme
from website import designs
from website.models import Website, WebsiteDomain

pytestmark = pytest.mark.django_db(transaction=True)
JSON = "application/json"

PALETTE = {
    "primary_color": "#05487a",
    "accent_color": "#032e52",
    "primary_color_name": "Blau",
    "accent_color_name": "Dunkelblau",
    "primary_color_use": "Leitfarbe",
    "extra_colors": [
        {"color": "#3c3d3e", "name": "Anthrazit", "use": "Fließtext"},
        {"color": "#5c5d5e", "name": "Grau", "use": "Sekundärtext, Linien"},
        {"color": "#eef2f6", "name": "Hellblau-Grau", "use": "Flächen"},
        {"color": "#ffffff", "name": "Weiß", "use": "Hintergrund"},
    ],
    "gradients": [
        {"name": "Blauverlauf", "from": 0, "to": 1, "direction": "right"},
        {"name": "Grauverlauf", "from": 2, "to": 3},
    ],
}


def _url(org):
    return f"/api/orgs/{org.pk}/theme/"


class TestPaletteMitVerlaeufen:
    def test_speichern_und_effektiv(self, api, orgs, board_a):
        resp = api(board_a).patch(_url(orgs["a"]), PALETTE, content_type=JSON)
        assert resp.status_code == 200, resp.content
        data = resp.json()
        assert data["primary_color_use"] == "Leitfarbe"
        assert data["gradients"][1]["direction"] == "right"
        eff = data["effective"]
        assert [p["use"] for p in eff["palette"]] == [
            "Leitfarbe",
            "",
            "Fließtext",
            "Sekundärtext, Linien",
            "Flächen",
            "Hintergrund",
        ]
        blue, grey = eff["gradients"]
        assert blue["colors"] == ["#05487a", "#032e52"] and blue["on_color"] == "#ffffff"
        assert grey["name"] == "Grauverlauf" and grey["contrast"] >= 4.5

    @pytest.mark.parametrize(
        "bad",
        [
            [{"from": 0, "to": 0}],
            [{"from": 0, "to": 6}],
            [{"from": "0", "to": 1}],
            [{"from": 0, "to": 1, "direction": "schraeg"}],
            [{"from": 0, "to": 1}] * 3,
            {"from": 0, "to": 1},
        ],
    )
    def test_falsche_verlaeufe_abgelehnt(self, api, orgs, board_a, bad):
        resp = api(board_a).patch(_url(orgs["a"]), {"gradients": bad}, content_type=JSON)
        assert resp.status_code == 400

    def test_verwendung_zu_lang(self, api, orgs, board_a):
        c = api(board_a)
        resp = c.patch(_url(orgs["a"]), {"primary_color_use": "x" * 61}, content_type=JSON)
        assert resp.status_code == 400
        extra = [{"color": "#3c3d3e", "name": "", "use": "x" * 61}]
        resp = c.patch(_url(orgs["a"]), {"extra_colors": extra}, content_type=JSON)
        assert resp.status_code == 400

    def test_verlauf_ohne_palettenplatz_entfaellt(self, orgs):
        club = orgs["a"]
        club.primary_color = "#05487a"
        club.gradients = [{"name": "", "from": 0, "to": 4, "direction": "right"}]
        club.save()
        assert effective_theme(club.ancestors())["gradients"] == []

    def test_verlaeufe_erben_mit_der_hauptfarbe(self, orgs):
        club = orgs["a"]
        club.primary_color = "#05487a"
        club.accent_color = "#032e52"
        club.gradients = [{"name": "Blau", "from": 0, "to": 1, "direction": "right"}]
        club.save()
        unit = Department.objects.create(organization=club, parent=club, name="Jägerzug")
        assert len(effective_theme(unit.ancestors())["gradients"]) == 1
        unit.primary_color = "#123e7a"
        unit.save()
        assert effective_theme(unit.ancestors())["gradients"] == []


class TestRollen:
    PALETTE = [
        {"color": "#05487a", "on_color": "#ffffff", "name": ""},
        {"color": "#032e52", "on_color": "#ffffff", "name": ""},
        {"color": "#3c3d3e", "on_color": "#ffffff", "name": ""},
        {"color": "#eef2f6", "on_color": "#1d2421", "name": ""},
    ]
    GRADIENTS = [
        {
            "name": "Blau",
            "colors": ["#05487a", "#032e52"],
            "on_color": "#ffffff",
            "direction": "right",
        },
    ]

    def test_verlauf_nur_fuer_flaechen_und_linien(self):
        roles = {"classic": {"header": "g0", "nav": "g0", "line": "g1", "text": "g0"}}
        assert designs.normalize_color_roles(roles) == {"classic": {"header": "g0", "line": "g1"}}

    def test_verlauf_aufgeloest(self):
        roles = {"classic": {"header": "g0", "line": "g1"}}
        colors = designs.resolve("classic", self.PALETTE, roles, None, self.GRADIENTS)
        assert colors["header"] == {
            "color": "#05487a",
            "on_color": "#ffffff",
            "gradient": {"from": "#05487a", "to": "#032e52", "direction": "right"},
        }
        # Zweiter Verlauf fehlt: Vorgabe des Designs
        assert colors["line"] == {"color": "#032e52", "on_color": "#ffffff"}
        # Ohne Verläufe (ältere Aufrufer) ebenfalls die Vorgabe
        assert "gradient" not in designs.resolve("classic", self.PALETTE, roles)["header"]

    def test_text_flaechen_hintergrund_nur_wenn_gewaehlt(self):
        assert "text" not in designs.resolve("stage", self.PALETTE)
        roles = {"stage": {"text": 2, "surface": 3, "background": "light", "muted": 5}}
        colors = designs.resolve("stage", self.PALETTE, roles)
        assert colors["text"]["color"] == "#3c3d3e"
        assert colors["surface"]["color"] == "#eef2f6"
        assert colors["background"]["color"] == "#ffffff"
        # Platz 5 gibt es in dieser Palette nicht: Rolle entfällt, das Design bleibt
        assert "muted" not in colors

    def test_katalog_kennt_neue_rollen(self):
        roles = designs.catalog()[0]["roles"]
        keys = [r["key"] for r in roles]
        assert keys[-4:] == ["text", "muted", "surface", "background"]
        assert next(r for r in roles if r["key"] == "header")["gradient"] is True
        assert next(r for r in roles if r["key"] == "nav")["gradient"] is False


@pytest.fixture
def site(orgs):
    org = orgs["a"]
    org.primary_color = "#05487a"
    org.accent_color = "#032e52"
    org.gradients = [{"name": "Blau", "from": 0, "to": 1, "direction": "right"}]
    org.save()
    site = Website.objects.create(
        organization=org,
        public_key="schluessel-v",
        state=Website.State.PUBLIC,
        privacy_published_text="Datenschutz (erfunden)",
        color_roles={"classic": {"header": "g0", "surface": 1}},
    )
    WebsiteDomain.objects.create(organization=org, website=site, hostname="www.verlauf.example")
    return site


def test_schnittstelle_liefert_verlauf(site):
    data = Client().get("/api/public/site/v1/schluessel-v/").json()
    header = data["designs"]["classic"]["header"]
    assert header["gradient"] == {"from": "#05487a", "to": "#032e52", "direction": "right"}
    assert data["designs"]["classic"]["surface"]["color"] == "#032e52"


def test_verwaltung_liefert_verlaeufe(api, orgs, board_a, site):
    data = api(board_a).get(f"/api/orgs/{orgs['a'].pk}/website/").json()
    assert data["gradients"][0]["name"] == "Blau"
    assert data["website"]["design_colors"]["classic"]["header"]["gradient"]["to"] == "#032e52"


def test_abschnitt_mit_verlauf_als_hintergrund():
    from website import home

    assert home._layout({"bg": "g1"}, "events")["bg"] == "g1"
    assert home._layout({"bg": "g2"}, "events")["bg"] == "none"


def test_schnittstelle_liefert_verlaeufe_fuer_abschnitte(site):
    data = Client().get("/api/public/site/v1/schluessel-v/").json()
    assert data["gradients"] == [
        {"colors": ["#05487a", "#032e52"], "on_color": "#ffffff", "direction": "right"}
    ]
