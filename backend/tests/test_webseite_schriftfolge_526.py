"""Eigene Schriftfolge der Webseite (#526): nur Namen lokal installierter Schriften, kein freies
CSS. Alle Daten erfunden."""

import pytest

from website import style
from website.models import Website

from .factories import give_role, make_user

KEY = "schrift-a"


def test_schriftfolge_wird_vereinheitlicht():
    assert style.font_stack(" Lucida Sans ,Lucida  Grande,, Segoe UI, Arial ") == (
        "Lucida Sans, Lucida Grande, Segoe UI, Arial"
    )
    # Anführungszeichen werden entfernt, doppelte Namen fallen weg, Ersatzfamilie bleibt am Ende
    assert style.font_stack('"Source Sans 3", serif, source sans 3') == "Source Sans 3, serif"
    assert style.font_stack(["Lucida Sans", "Arial"]) == "Lucida Sans, Arial"
    assert style.font_stack("") == ""
    assert style.font_stack(None) == ""
    assert style.font_stack("sans-serif") == ""


@pytest.mark.parametrize(
    "value",
    [
        "Arial; color: red",
        "x{y}",
        "Arial)",
        "a/b",
        "-Arial",
        "A" * 41,
        "A, B, C, D, E, F, G",
        42,
    ],
)
def test_nur_schriftnamen(value):
    with pytest.raises(ValueError):
        style.font_stack(value)


def test_validate_und_katalog():
    assert style.validate({"font_family": "Lucida Sans, Arial", "heading_font_family": ""}) == {
        "font_family": "Lucida Sans, Arial"
    }
    with pytest.raises(ValueError):
        style.validate({"font_family": "url(x)"})
    options = style.catalog()["options"]
    assert options["font_family"] == "fonts"
    assert options["heading_font_family"] == "fonts"


@pytest.mark.django_db(transaction=True)
def test_speichern_und_oeffentlich(orgs, api):
    club = orgs["a"]
    club.enabled_modules = ["members", "events", "website"]
    club.save()
    site = Website.objects.create(organization=club, public_key=KEY, state="maintenance")
    user = make_user("web-schrift@example.org")
    give_role(user, club, permissions=["website.manage"], name="Webseite")
    resp = api(user).put(
        f"/api/orgs/{club.pk}/website/",
        {"style": {"font": "clear", "font_family": "Lucida Sans,Segoe UI"}},
        "application/json",
    )
    assert resp.status_code == 200, resp.content
    site.refresh_from_db()
    assert site.style == {"font": "clear", "font_family": "Lucida Sans, Segoe UI"}
    assert style.public(site.style)["font_family"] == "Lucida Sans, Segoe UI"
    resp = api(user).put(
        f"/api/orgs/{club.pk}/website/",
        {"style": {"font_family": 'Arial"; }'}},
        "application/json",
    )
    assert resp.status_code == 400
