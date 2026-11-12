"""Gesamtaudit 11.11.2026, S-03: Fehlversuche Fremder sperren den Inhaber nicht mehr aus."""

import pytest
from django.core import mail, signing
from django.test import Client

from accounts import known_device

from .factories import PASSWORD, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"
LOGIN = "/_allauth/browser/v1/auth/login"
EMAIL = "kasse@example.org"


def anmelden(
    client: Client, password: str = PASSWORD, email: str = EMAIL, ip: str = "198.51.100.20"
):
    return client.post(
        LOGIN,
        {"email": email, "password": password},
        content_type=JSON,
        REMOTE_ADDR="172.18.0.5",
        HTTP_X_FORWARDED_FOR=ip,
    )


def angriff(email: str = EMAIL, ip: str = "203.0.113.9", versuche: int = 6) -> None:
    for _ in range(versuche):
        assert anmelden(Client(), "falsch", email, ip).status_code == 400


@pytest.fixture
def bekannt() -> Client:
    """Browser, mit dem sich das Konto schon einmal angemeldet hat (danach abgemeldet)."""
    make_user(EMAIL)
    client = Client()
    assert anmelden(client).status_code == 200
    assert known_device.COOKIE in client.cookies
    client.cookies.pop("sessionid", None)
    return client


def test_cookie_nach_erfolgreicher_anmeldung(bekannt):
    cookie = bekannt.cookies[known_device.COOKIE]
    assert cookie["httponly"] and cookie["samesite"] == "Lax"
    assert int(cookie["max-age"]) == known_device.MAX_AGE
    # Kein Klartext: weder Adresse noch Kontonummer
    assert "kasse" not in cookie.value
    # Fehlgeschlagene Anmeldung: kein Cookie
    fremd = Client()
    assert anmelden(fremd, "falsch").status_code == 400
    assert known_device.COOKIE not in fremd.cookies


def test_fremde_fehlversuche_sperren_bekanntes_geraet_nicht(bekannt):
    angriff()
    # Fremdes Gerät: wie bisher gesperrt, auch mit richtigem Passwort
    gesperrt = anmelden(Client(), ip="198.51.100.77")
    assert gesperrt.status_code == 400
    assert "Passkey" in gesperrt.content.decode()
    # Bekanntes Gerät: kommt hinein
    assert anmelden(bekannt).status_code == 200


def test_cookie_gilt_nur_fuer_das_eigene_konto(bekannt):
    make_user("vorstand@example.org")
    angriff("vorstand@example.org")
    assert anmelden(bekannt, email="vorstand@example.org").status_code == 400


def test_gefaelschtes_cookie_hilft_nicht():
    make_user(EMAIL)
    angriff()
    client = Client()
    falsch = signing.dumps(
        {"i": "x", "a": [known_device._account(EMAIL)]}, salt="anderes-salz", compress=True
    )
    client.cookies[known_device.COOKIE] = falsch
    assert anmelden(client).status_code == 400
    client.cookies[known_device.COOKIE] = "unsinn"
    assert anmelden(client).status_code == 400


def test_bekanntes_geraet_hat_eigene_grenze(bekannt):
    """Ein gestohlenes Cookie erlaubt nicht mehr Versuche als bisher."""
    for _ in range(6):
        assert anmelden(bekannt, "falsch").status_code == 400
    assert anmelden(bekannt).status_code == 400
    # … und sperrt dabei weder fremde noch andere bekannte Geräte des Kontos
    assert anmelden(Client(), ip="198.51.100.88").status_code == 200


def test_mehrere_konten_auf_einem_geraet(bekannt):
    make_user("zweites@example.org")
    assert anmelden(bekannt, email="zweites@example.org").status_code == 200
    bekannt.cookies.pop("sessionid", None)
    angriff()
    angriff("zweites@example.org", ip="203.0.113.10")
    assert anmelden(bekannt).status_code == 200
    bekannt.cookies.pop("sessionid", None)
    assert anmelden(bekannt, email="zweites@example.org").status_code == 200


def test_mail_an_den_inhaber_hoechstens_einmal(bekannt):
    mail.outbox.clear()
    angriff(versuche=9)
    hinweise = [m for m in mail.outbox if m.to == [EMAIL]]
    assert len(hinweise) == 1
    assert hinweise[0].subject == "Zu viele Fehlversuche bei der Anmeldung"
    assert "fremden Geräten" in hinweise[0].body and "/anmelden" in hinweise[0].body


def test_keine_mail_fuer_unbekannte_adresse():
    mail.outbox.clear()
    angriff("niemand@example.org", versuche=9)
    assert mail.outbox == []
