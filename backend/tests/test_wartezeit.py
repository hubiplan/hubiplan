"""Zu viele Versuche: Die Meldung nennt die Wartezeit in Minuten (statt nur „später“)."""

import pytest
from django.core.cache import cache
from django.utils import translation

from core import ratelimit
from core.ratelimit import retry_after, too_many, wait_message

from .factories import PASSWORD, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture(autouse=True)
def _leer():
    cache.clear()
    yield
    cache.clear()


def test_festes_fenster_ab_dem_ersten_versuch(monkeypatch):
    jetzt = [1000.0]
    monkeypatch.setattr(ratelimit.time, "time", lambda: jetzt[0])
    assert not too_many("probe", 2, 3600)
    jetzt[0] += 600  # zehn Minuten später: das Fenster verlängert sich nicht
    assert not too_many("probe", 2, 3600)
    assert too_many("probe", 2, 3600)
    assert retry_after("probe") == 3000
    assert wait_message("probe") == (
        "Zu viele Versuche. Bitte in etwa 50 Minuten erneut versuchen."
    )


def test_minuten_aufgerundet_und_einzahl(monkeypatch):
    jetzt = [0.0]
    monkeypatch.setattr(ratelimit.time, "time", lambda: jetzt[0])
    too_many("probe", 0, 120)
    jetzt[0] = 61  # noch 59 Sekunden
    assert wait_message("probe", "aufrufe") == (
        "Zu viele Aufrufe. Bitte in etwa einer Minute erneut versuchen."
    )
    jetzt[0] = 1  # noch 119 Sekunden: aufgerundet auf zwei Minuten
    assert "in etwa 2 Minuten" in wait_message("probe")


def test_ohne_bekanntes_ende_bleibt_es_bei_spaeter():
    assert retry_after("unbekannt") is None
    assert wait_message("unbekannt") == "Zu viele Versuche. Bitte später erneut."


def test_englisch():
    too_many("probe", 0, 3600)
    with translation.override("en"):
        text = wait_message("probe")
    assert text == "Too many attempts. Please try again in about 60 minutes."


def test_email_aendern_nennt_wartezeit_und_retry_after(api):
    u = make_user("karla@example.org")
    c = api(u)
    for n in range(5):
        r = c.post(
            "/api/me/email/",
            {"email": f"neu{n}@example.org", "password": "falsch"},
            content_type=JSON,
        )
        assert r.status_code == 400
    # Falsches Passwort: Hinweis, dass nicht das Postfach-Passwort gemeint ist
    assert "E-Mail-Postfachs" in r.json()["password"][0]
    r = c.post(
        "/api/me/email/", {"email": "neu@example.org", "password": PASSWORD}, content_type=JSON
    )
    assert r.status_code == 429
    assert r.json()["detail"] == "Zu viele Versuche. Bitte in etwa 60 Minuten erneut versuchen."
    assert 3500 < int(r["Retry-After"]) <= 3600


def test_passwort_aendern_nennt_wartezeit(api):
    u = make_user("karla@example.org")
    c = api(u)
    for _ in range(10):
        c.post(
            "/api/me/password/",
            {"current_password": "falsch", "new_password": "Ganz-Neues-Passwort-42"},
            content_type=JSON,
        )
    r = c.post(
        "/api/me/password/",
        {"current_password": PASSWORD, "new_password": "Ganz-Neues-Passwort-42"},
        content_type=JSON,
    )
    assert r.status_code == 429
    assert "Minuten" in r.json()["detail"]
    assert r.has_header("Retry-After")
