"""Eingeladene Konten können die Zwei-Faktor-Anmeldung einrichten (#599).

Erfundene Daten. Geprüft: Ein Link an die Anmelde-E-Mail (Einladung, „Passwort vergessen“,
Anmeldelink) bestätigt die Adresse; schon das Anfordern legt keine unbestätigte Adresszeile
an; die Datenmigration bestätigt Adresszeilen angemeldeter Konten.
"""

import importlib
import re

import pytest
from allauth.account.models import EmailAddress
from allauth.mfa.internal.flows.add import validate_can_add_authenticator
from django.apps import apps
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import Client
from django.utils import timezone

from .conftest import csrf_headers
from .factories import make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"
AUTH = "/_allauth/browser/v1"


def _password_from_key(client, key: str, password: str) -> None:
    resp = client.post(
        f"{AUTH}/auth/password/reset",
        {"key": key, "password": password},
        content_type=JSON,
        headers=csrf_headers(client),
    )
    assert resp.status_code in (200, 401), resp.content


def test_einladung_bestaetigt_adresse_und_2fa_geht(client):
    from accounts.invitations import password_link

    user = make_user("eingeladen-2fa@example.org")
    user.set_unusable_password()
    user.save()
    key = password_link(user).rsplit("/", 1)[1]
    # Altbestand: Frühere Fassungen legten beim Erzeugen des Links eine unbestätigte Zeile an
    EmailAddress.objects.create(user=user, email=user.email, verified=False, primary=True)
    with pytest.raises(ValidationError):
        validate_can_add_authenticator(user)

    _password_from_key(client, key, "Mein-Erstes-Passwort-7")

    assert EmailAddress.objects.get(user=user).verified
    validate_can_add_authenticator(user)  # keine Fehlermeldung mehr


def test_passwort_vergessen_anfordern_sperrt_2fa_nicht(client):
    user = make_user("vergessen-2fa@example.org")
    resp = client.post(
        f"{AUTH}/auth/password/request",
        {"email": user.email},
        content_type=JSON,
        headers=csrf_headers(client),
    )
    assert resp.status_code == 200, resp.content
    assert not EmailAddress.objects.filter(user=user, verified=False).exists()
    validate_can_add_authenticator(user)

    key = re.search(r"/passwort-zuruecksetzen/(\S+)", mail.outbox[-1].body).group(1)
    _password_from_key(client, key, "Ganz-Neues-Passwort-42")
    user.refresh_from_db()
    assert user.check_password("Ganz-Neues-Passwort-42")  # Link gilt weiter


def test_anmeldelink_bestaetigt_adresse():
    from portal.services import create_login_link

    user = make_user("anmeldelink-2fa@example.org")
    EmailAddress.objects.create(user=user, email=user.email, verified=False, primary=True)
    token = create_login_link(user).rsplit("/", 1)[1]
    browser = Client()
    resp = browser.post(
        f"/api/public/login-link/{token}/", content_type=JSON, headers=csrf_headers(browser)
    )
    assert resp.status_code == 200, resp.content
    assert EmailAddress.objects.get(user=user).verified


def test_migration_bestaetigt_nur_angemeldete_konten():
    migration = importlib.import_module("accounts.migrations.0021_einladung_adresse_bestaetigt")
    angemeldet = make_user("angemeldet-2fa@example.org", last_login=timezone.now())
    offen = make_user("offen-2fa@example.org")
    EmailAddress.objects.create(
        user=angemeldet, email="Angemeldet-2FA@example.org", verified=False, primary=True
    )
    EmailAddress.objects.create(user=offen, email=offen.email, verified=False, primary=True)

    migration.adressen_bestaetigen(apps, None)

    assert EmailAddress.objects.get(user=angemeldet).verified
    assert not EmailAddress.objects.get(user=offen).verified
