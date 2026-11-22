"""Hinweis an das Konto bei einer Anmeldung auf einem bisher unbekannten Gerät (Härtung 22.11.).

Erfundene Daten. Geprüft: Mail beim neuen Gerät, keine beim bekannten, keine bei der allerersten
Anmeldung, höchstens eine am Tag je Programm, nichts Fremdes aus der Kennung des Aufrufers in
der Mail, abschaltbar.
"""

import re

import pytest
from django.core import mail
from django.test import Client
from django.utils import timezone

from accounts import known_device
from accounts.models import User

from .factories import PASSWORD, make_user

pytestmark = pytest.mark.django_db(transaction=True)
JSON = "application/json"
LOGIN = "/_allauth/browser/v1/auth/login"
EMAIL = "schriftfuehrung@example.org"
FIREFOX = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0"
CHROME_ANDROID = (
    "Mozilla/5.0 (Linux; Android 16; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Mobile Safari/537.36"
)
BETREFF = "Neue Anmeldung bei HUBIplan"


@pytest.fixture(autouse=True)
def _hinweis_an(settings):
    settings.LOGIN_NOTICE = True


def anmelden(client: Client, agent: str = FIREFOX, email: str = EMAIL):
    return client.post(
        LOGIN, {"email": email, "password": PASSWORD}, content_type=JSON, HTTP_USER_AGENT=agent
    )


def hinweise() -> list:
    return [m for m in mail.outbox if m.subject == BETREFF]


@pytest.fixture
def konto() -> User:
    """Konto, das sich früher schon einmal angemeldet hat (irgendwo anders)."""
    user = make_user(EMAIL, first_name="Erika", last_name="Muster")
    User.objects.filter(pk=user.pk).update(last_login=timezone.now())
    mail.outbox.clear()
    return user


def test_neues_geraet_meldet_sich_beim_inhaber(konto):
    assert anmelden(Client()).status_code == 200
    (m,) = hinweise()
    assert m.to == [EMAIL]
    assert "Firefox unter Windows" in m.body
    assert "Hallo Erika Muster" in m.body
    assert "ändere dein Passwort" in m.body
    # kein Link zum Handeln (Impressum und Datenschutz im Fuß ausgenommen)
    links = [
        u
        for u in re.findall(r"https?://\S+", m.body)
        if not u.rstrip("/").endswith(("/impressum", "/datenschutz"))
    ]
    assert links == []


def test_bekanntes_geraet_bleibt_still(konto):
    client = Client()
    assert anmelden(client).status_code == 200
    assert known_device.COOKIE in client.cookies
    mail.outbox.clear()
    client.cookies.pop("sessionid", None)
    assert anmelden(client).status_code == 200
    assert hinweise() == []


def test_erste_anmeldung_ueberhaupt_bleibt_still():
    make_user(EMAIL)
    mail.outbox.clear()
    assert anmelden(Client()).status_code == 200
    assert hinweise() == []


def test_falsches_passwort_meldet_nichts(konto):
    r = Client().post(
        LOGIN, {"email": EMAIL, "password": "falsch"}, content_type=JSON, HTTP_USER_AGENT=FIREFOX
    )
    assert r.status_code == 400
    assert hinweise() == []


def test_hoechstens_ein_hinweis_am_tag_je_programm(konto):
    for _ in range(3):  # jedes Mal ohne Cookie, z. B. privates Fenster
        assert anmelden(Client()).status_code == 200
    assert len(hinweise()) == 1
    # Ein anderes Programm fällt trotzdem auf
    assert anmelden(Client(), CHROME_ANDROID).status_code == 200
    assert len(hinweise()) == 2
    assert "Chrome unter Android" in hinweise()[1].body


def test_kennung_des_aufrufers_kommt_nie_woertlich_in_die_mail(konto):
    boese = "Firefox Windows https://boese.example/klick <b>Jetzt bestätigen</b>"
    assert anmelden(Client(), boese).status_code == 200
    (m,) = hinweise()
    assert "boese.example" not in m.body and "<b>" not in m.body
    assert "Firefox unter Windows" in m.body


def test_abschaltbar(konto, settings):
    settings.LOGIN_NOTICE = False
    assert anmelden(Client()).status_code == 200
    assert hinweise() == []


@pytest.mark.parametrize(
    ("agent", "text"),
    [
        (FIREFOX, "Firefox unter Windows"),
        (CHROME_ANDROID, "Chrome unter Android"),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/19.0 Safari/605.1.15",
            "Safari unter macOS",
        ),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0",
            "Edge unter Windows",
        ),
        ("HUBIplan-Android/1.11.1", "HUBIplan-App unter Android"),
        ("curl/8.5.0", "unbekanntes Programm"),
        ("", "unbekanntes Programm"),
    ],
)
def test_beschreibung_des_programms(agent, text):
    assert known_device.describe_client(agent) == text
