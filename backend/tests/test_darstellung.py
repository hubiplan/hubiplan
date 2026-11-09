"""Darstellung der Web-App am eigenen Konto: wie Gerät, hell oder dunkel (X-02)."""

import pytest
from django.test import Client

from accounts.models import User

from .conftest import csrf_headers
from .factories import make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"
URL = "/api/me/appearance/"


def login(email: str) -> tuple[Client, dict[str, str]]:
    make_user(email)
    c = Client(enforce_csrf_checks=True)
    c.force_login(User.objects.get(email=email))
    return c, csrf_headers(c)


def test_neue_konten_folgen_dem_geraet():
    c, _ = login("karla@example.org")
    assert c.get(URL).json() == {"color_scheme": "auto"}


def test_waehlen_gilt_nur_fuer_das_eigene_konto():
    c, h = login("karla@example.org")
    make_user("otto@example.org")
    resp = c.patch(URL, {"color_scheme": "dark"}, content_type=JSON, headers=h)
    assert resp.status_code == 200
    assert resp.json() == {"color_scheme": "dark"}
    assert User.objects.get(email="karla@example.org").color_scheme == "dark"
    assert User.objects.get(email="otto@example.org").color_scheme == "auto"


def test_unbekannte_wahl_abgelehnt():
    c, h = login("karla@example.org")
    assert c.patch(URL, {"color_scheme": "lila"}, content_type=JSON, headers=h).status_code == 400
    assert User.objects.get(email="karla@example.org").color_scheme == "auto"


def test_ohne_csrf_und_ohne_anmeldung_abgelehnt():
    c, _ = login("karla@example.org")
    assert c.patch(URL, {"color_scheme": "dark"}, content_type=JSON).status_code == 403
    assert Client().get(URL).status_code in (401, 403)


def test_datenschutzhinweise_nennen_die_darstellung():
    from organizations.imprint_generator import platform_privacy

    assert "gewählte Darstellung (wie das Gerät, hell oder dunkel)" in platform_privacy()
