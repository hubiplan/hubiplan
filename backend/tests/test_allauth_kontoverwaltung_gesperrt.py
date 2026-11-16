"""allauths eigene E-Mail- und Passwortverwaltung ist gesperrt (Gesamtaudit 15.11., AUTH-02).

Vorher: Mit einer übernommenen Sitzung ließ sich ohne Passwort eine zweite Adresse anhängen;
„Passwort vergessen“ an diese Adresse setzte ein neues Passwort (dauerhafte Kontoübernahme).
"""

from __future__ import annotations

import importlib

import pytest
from allauth.account.models import EmailAddress
from django.apps import apps as django_apps
from django.test import Client

from .conftest import csrf_headers
from .factories import make_user

pytestmark = pytest.mark.django_db

JSON = "application/json"
ANGREIFER = "angreifer@example.net"


@pytest.mark.parametrize("client_art", ["browser", "app"])
@pytest.mark.parametrize("pfad", ["account/email", "account/phone", "account/password/change"])
def test_allauth_kontoverwaltung_gesperrt(client_art, pfad):
    opfer = make_user("mitglied@example.org")
    sitzung = Client()
    sitzung.force_login(opfer)
    url = f"/_allauth/{client_art}/v1/{pfad}"
    assert sitzung.get(url).status_code == 404
    resp = sitzung.post(url, {"email": ANGREIFER, "new_password": "x" * 20}, content_type=JSON)
    assert resp.status_code == 404
    assert not EmailAddress.objects.filter(email=ANGREIFER).exists()


def test_keine_zweite_adresse_und_kein_ruecksetzlink_an_fremde(mailoutbox):
    opfer = make_user("mitglied@example.org")
    sitzung = Client(raise_request_exception=False)
    sitzung.force_login(opfer)
    sitzung.post("/_allauth/browser/v1/account/email", {"email": ANGREIFER}, content_type=JSON)
    anonym = Client(raise_request_exception=False)
    anonym.post(
        "/_allauth/browser/v1/auth/password/request",
        {"email": ANGREIFER},
        content_type=JSON,
        headers=csrf_headers(anonym),
    )
    # Höchstens die allauth-Mail „kein Konto zu dieser Adresse“, nie ein Rücksetzlink
    an_angreifer = [m for m in mailoutbox if ANGREIFER in m.to]
    assert not [m for m in an_angreifer if "passwort-zuruecksetzen" in m.body]


def test_migration_entfernt_zusatzadressen_und_behaelt_anmeldeadresse():
    opfer = make_user("Mitglied@Example.org")
    EmailAddress.objects.filter(user=opfer).delete()
    EmailAddress.objects.create(user=opfer, email="mitglied@example.org", primary=True)
    EmailAddress.objects.create(user=opfer, email=ANGREIFER, primary=False, verified=False)
    mod = importlib.import_module("accounts.migrations.0018_zusatzadressen_entfernen")
    mod.zusatzadressen_entfernen(django_apps, None)
    assert list(EmailAddress.objects.filter(user=opfer).values_list("email", flat=True)) == [
        "mitglied@example.org"
    ]
