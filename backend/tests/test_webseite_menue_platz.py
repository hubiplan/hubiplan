"""Webseite #75: Menüpunkte nur im Fuß oder im Menü und im Fuß, „Start“ ausblendbar und Lage
der Suche als Stilregler. Alle Daten erfunden."""

import pytest

from website import menu, style
from website.models import Website

from .test_webseite_menue_links import client_web, club, nav, put, site  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


class TestPlatz:
    def test_kontakt_nur_im_fuss(self, club, site, client_web):  # noqa: F811
        resp = put(client_web, club, {"menu_places": {"contact": "footer"}})
        assert resp.status_code == 200, resp.content
        contact = next(n for n in nav(site) if n["key"] == "contact")
        assert contact["place"] == "footer"
        assert not any(n.get("place") for n in nav(site) if n["key"] != "contact")

    def test_menue_und_fuss_und_zurueck(self, club, site, client_web):  # noqa: F811
        assert put(client_web, club, {"menu_places": {"contact": "both"}}).status_code == 200
        assert next(n for n in nav(site) if n["key"] == "contact")["place"] == "both"
        # „main“ oder leer: wieder nur im Menü, gespeichert wird nichts
        assert put(client_web, club, {"menu_places": {"contact": "main"}}).status_code == 200
        assert Website.objects.get(pk=site.pk).menu_places == {}
        assert "place" not in next(n for n in nav(site) if n["key"] == "contact")

    def test_ungueltig_abgelehnt(self, club, site, client_web):  # noqa: F811
        for value in (
            {"contact": "oben"},
            {"group:history": "footer"},
            {"gibtsnicht": "footer"},
            ["contact"],
        ):
            assert put(client_web, club, {"menu_places": value}).status_code == 400, value

    def test_neuer_link_in_einer_aenderung(self, club, site, client_web):  # noqa: F811
        resp = put(
            client_web,
            club,
            {
                "block_names": {"link:1": "Kreisverband"},
                "menu_links": {"link:1": "https://kreis.example.org"},
                "menu_places": {"link:1": "footer"},
            },
        )
        assert resp.status_code == 200, resp.content
        assert next(n for n in nav(site) if n["key"] == "link")["place"] == "footer"

    def test_unterpunkt_kommt_nicht_in_den_fuss(self, club, site):  # noqa: F811
        site.menu_places = {"contact": "footer"}
        site.menu = [{"key": "events", "children": [{"key": "contact"}]}]
        site.save()
        events = next(n for n in nav(site) if n["key"] == "events")
        assert not any(c.get("place") for c in events["children"])

    def test_alte_werte_ohne_fehler(self, club, site):  # noqa: F811
        site.menu_places = {"contact": "irgendwo", "events": 5}
        site.save()
        assert menu.places(Website.objects.get(pk=site.pk)) == {}


def test_stilregler_start_und_suche():
    assert style.validate({"nav_start": False, "search": "header"}) == {
        "nav_start": False,
        "search": "header",
    }
    for bad in ({"search": "off"}, {"nav_start": "aus"}):
        with pytest.raises(ValueError):
            style.validate(bad)
