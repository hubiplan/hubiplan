"""Laufzeit der Anmeldung: Rest abfragen und „Angemeldet bleiben“ (UX-Audit 16.11., VW-04)."""

from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.sessions.models import Session
from django.test import Client
from django.utils import timezone

from accounts.models import User

from .conftest import csrf_headers
from .factories import make_user

pytestmark = pytest.mark.django_db
URL = "/api/me/session/"


def login(email: str = "karla@example.org") -> tuple[Client, dict[str, str]]:
    make_user(email)
    c = Client(enforce_csrf_checks=True)
    c.force_login(User.objects.get(email=email))
    return c, csrf_headers(c)


def expire_in(client: Client, seconds: int) -> None:
    Session.objects.filter(session_key=client.session.session_key).update(
        expire_date=timezone.now() + timedelta(seconds=seconds)
    )


def test_frische_anmeldung_hat_fast_die_volle_laufzeit():
    c, _ = login()
    rest = c.get(URL).json()["expires_in"]
    assert settings.SESSION_COOKIE_AGE - 60 <= rest <= settings.SESSION_COOKIE_AGE


def test_rest_folgt_dem_gespeicherten_ablauf():
    c, _ = login()
    expire_in(c, 300)
    rest = c.get(URL).json()["expires_in"]
    assert 240 <= rest <= 300


def test_angemeldet_bleiben_verlaengert_auf_die_volle_laufzeit():
    c, h = login()
    expire_in(c, 300)
    resp = c.post(URL, headers=h)
    assert resp.status_code == 200
    assert resp.json() == {"expires_in": settings.SESSION_COOKIE_AGE}
    rest = c.get(URL).json()["expires_in"]
    assert rest >= settings.SESSION_COOKIE_AGE - 60


def test_abfragen_allein_verlaengert_nicht():
    c, _ = login()
    expire_in(c, 300)
    c.get(URL)
    assert c.get(URL).json()["expires_in"] <= 300


def test_ohne_anmeldung_keine_auskunft():
    c = Client()
    assert c.get(URL).status_code in (401, 403)
