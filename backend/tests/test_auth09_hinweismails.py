"""Hinweismails bei Änderungen an den Anmeldedaten (Gesamtaudit 15.11., AUTH-09).

Erfundene Daten. Geprüft: Zwei-Faktor einrichten und entfernen, neue Wiederherstellungscodes,
abgeschlossener E-Mail-Wechsel (alte und neue Adresse). Die Mails enthalten weder Geheimnisse
noch Links zum Bestätigen.
"""

import re

import pytest
from allauth.mfa import signals
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.core import mail
from django.test import Client

from .conftest import csrf_headers
from .factories import PASSWORD, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


def _links(body: str) -> list[str]:
    """Links außer Impressum und Datenschutz im Fuß jeder Mail."""
    return [
        url
        for url in re.findall(r"https?://\S+", body)
        if not url.rstrip("/").endswith(("/impressum", "/datenschutz"))
    ]


def _signal(signal, user, authenticator):
    signal.send(sender=Authenticator, request=None, user=user, authenticator=authenticator)


def test_zwei_faktor_hinweise(django_capture_on_commit_callbacks):
    user = make_user("hinweis-2fa@example.org")
    secret = generate_totp_secret()
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        totp = TOTP.activate(user, secret).instance
        _signal(signals.authenticator_added, user, totp)
        recovery = Authenticator.objects.create(
            user=user, type=Authenticator.Type.RECOVERY_CODES, data={"seed": "x", "used_mask": 0}
        )
        _signal(signals.authenticator_added, user, recovery)  # kein eigener Hinweis
        _signal(signals.authenticator_reset, user, recovery)
        _signal(signals.authenticator_removed, user, totp)
    subjects = [m.subject for m in mail.outbox]
    assert subjects == [
        "Zwei-Faktor-Anmeldung eingerichtet",
        "Neue Wiederherstellungscodes",
        "Zwei-Faktor-Anmeldung entfernt",
    ]
    for m in mail.outbox:
        assert m.to == [user.email]
        assert secret not in m.body
        assert _links(m.body) == []  # kein Link zum Handeln


def test_email_wechsel_an_alte_und_neue_adresse(api, django_capture_on_commit_callbacks):
    user = make_user("alt-hinweis@example.org")
    r = api(user).post(
        "/api/me/email/",
        {"email": "neu-hinweis@example.org", "password": PASSWORD},
        content_type=JSON,
    )
    assert r.status_code == 201, r.json()
    confirm = next(m for m in mail.outbox if "neu-hinweis@example.org" in m.to)
    token = re.search(r"/konto/email/([\w-]+)", confirm.body).group(1)
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        assert Client().post(f"/api/public/email-confirm/{token}/").status_code == 200
    notices = [m for m in mail.outbox if m.subject == "Anmelde-E-Mail geändert"]
    assert sorted(a for m in notices for a in m.to) == [
        "alt-hinweis@example.org",
        "neu-hinweis@example.org",
    ]
    assert all(_links(m.body) == [] for m in notices)


AUTH = "/_allauth/browser/v1"


def _reset(client, email: str, password: str):
    resp = client.post(
        f"{AUTH}/auth/password/request",
        {"email": email},
        content_type=JSON,
        headers=csrf_headers(client),
    )
    assert resp.status_code == 200, resp.content
    key = re.search(r"/passwort-zuruecksetzen/(\S+)", mail.outbox[-1].body).group(1)
    mail.outbox.clear()
    resp = client.post(
        f"{AUTH}/auth/password/reset",
        {"key": key, "password": password},
        content_type=JSON,
        headers=csrf_headers(client),
    )
    assert resp.status_code in (200, 401), resp.content


def test_passwort_zurueckgesetzt(client, django_capture_on_commit_callbacks):
    from django.utils import timezone

    user = make_user("reset-hinweis@example.org")
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])
    with django_capture_on_commit_callbacks(execute=True):
        _reset(client, user.email, "Ganz-Neues-Passwort-42")
    notes = [m for m in mail.outbox if m.subject == "Passwort zurückgesetzt"]
    assert [m.to for m in notes] == [[user.email]]
    assert _links(notes[0].body) == []
    assert "Ganz-Neues-Passwort-42" not in notes[0].body


def test_erstes_passwort_aus_der_einladung_ohne_hinweis(client, django_capture_on_commit_callbacks):
    from accounts.invitations import password_link

    user = make_user("einladung-hinweis@example.org")
    user.set_unusable_password()
    user.save()
    key = password_link(user).rsplit("/", 1)[1]
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        resp = client.post(
            f"{AUTH}/auth/password/reset",
            {"key": key, "password": "Mein-Erstes-Passwort-7"},
            content_type=JSON,
            headers=csrf_headers(client),
        )
    assert resp.status_code in (200, 401), resp.content
    assert not [m for m in mail.outbox if m.subject == "Passwort zurückgesetzt"]


def test_passkey_hinweis_kommt_aus_passkeys(django_capture_on_commit_callbacks):
    """Passkeys meldet accounts/passkeys.py; hier kein zweiter Hinweis."""
    from allauth.mfa.models import Authenticator

    user = make_user("passkey-hinweis@example.org")
    passkey = Authenticator(user=user, type=Authenticator.Type.WEBAUTHN, data={"name": "Laptop"})
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        _signal(signals.authenticator_added, user, passkey)
        _signal(signals.authenticator_removed, user, passkey)
    assert len(mail.outbox) == 2, [m.subject for m in mail.outbox]
