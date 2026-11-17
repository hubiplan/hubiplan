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
