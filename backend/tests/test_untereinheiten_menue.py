"""Vereine ohne Untereinheiten blenden den Menüpunkt aus (Ralf 15.11.2026)."""

import pytest

pytestmark = pytest.mark.django_db
JSON = "application/json"


def _summary(api, user, org):
    return next(o for o in api(user).get("/api/me/organizations/").json() if o["id"] == org.pk)


def test_menuepunkt_standardmaessig_an_und_abschaltbar(api, orgs, board_a):
    club = orgs["a"]
    assert _summary(api, board_a, club)["units_in_menu"] is True
    resp = api(board_a).patch(f"/api/orgs/{club.pk}/", {"units_in_menu": False}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    assert resp.json()["units_in_menu"] is False
    club.refresh_from_db()
    assert club.units_in_menu is False
    assert _summary(api, board_a, club)["units_in_menu"] is False


def test_dachverband_behaelt_menuepunkt(orgs):
    from access.views import organization_summary

    fed = orgs["federation"]
    fed.units_in_menu = False
    fed.save(update_fields=["units_in_menu"])
    assert organization_summary(fed, set())["units_in_menu"] is True
