"""Anmeldung mit Passkey, Stufe P1 (konzepte/passkey-anmeldung.md). Erfundene Daten.

Ein kleiner Software-Authenticator (P-256, Bescheinigung „none“) spielt Handy bzw.
Passwortmanager: Er legt Passkeys an und unterschreibt Anmeldungen wie ein Browser.
"""

import base64
import hashlib
import json
import os

import pytest
from allauth.mfa.models import Authenticator
from allauth.mfa.webauthn.internal.auth import WebAuthn
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from django.core import mail
from django.test import Client
from fido2.cose import ES256
from fido2.webauthn import Aaguid, AttestationObject, AttestedCredentialData, AuthenticatorData

from accounts import passkeys
from accounts.mfa_policy import has_mfa
from peering.sso import session_auth

from .factories import PASSWORD, make_user

pytestmark = pytest.mark.django_db
AUTH = "/_allauth/browser/v1"
JSON = "application/json"
HOST = "testserver"


def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


class SoftKey:
    """Software-Passkey für eine Adresse (Relying Party)."""

    def __init__(self, rp_id: str = HOST, user=None):
        self.rp_id = rp_id
        self.origin = f"https://{rp_id}"
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.cred_id = os.urandom(16)
        self.user_handle = str(user.pk).encode() if user is not None else b""
        self.counter = 0

    def _client_data(self, kind: str, challenge: str) -> bytes:
        return json.dumps(
            {"type": kind, "challenge": challenge, "origin": self.origin, "crossOrigin": False}
        ).encode()

    def _rp_hash(self) -> bytes:
        return hashlib.sha256(self.rp_id.encode()).digest()

    def register(self, challenge: str = "AAAA") -> dict:
        flag = AuthenticatorData.FLAG
        credential = AttestedCredentialData.create(
            Aaguid.NONE, self.cred_id, ES256.from_cryptography_key(self.key.public_key())
        )
        data = AuthenticatorData.create(self._rp_hash(), flag.UP | flag.UV | flag.AT, 0, credential)
        return {
            "id": b64(self.cred_id),
            "rawId": b64(self.cred_id),
            "type": "public-key",
            "clientExtensionResults": {"credProps": {"rk": True}},
            "response": {
                "clientDataJSON": b64(self._client_data("webauthn.create", challenge)),
                "attestationObject": b64(bytes(AttestationObject.create("none", data, {}))),
                "transports": ["internal"],
            },
        }

    def sign(self, options: dict, *, verified: bool = True) -> dict:
        public_key = options.get("publicKey", options)
        flag = AuthenticatorData.FLAG
        self.counter += 1
        data = AuthenticatorData.create(
            self._rp_hash(), flag.UP | (flag.UV if verified else 0), self.counter
        )
        client_data = self._client_data("webauthn.get", public_key["challenge"])
        signature = self.key.sign(
            bytes(data) + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
        )
        return {
            "id": b64(self.cred_id),
            "rawId": b64(self.cred_id),
            "type": "public-key",
            "clientExtensionResults": {},
            "response": {
                "clientDataJSON": b64(client_data),
                "authenticatorData": b64(bytes(data)),
                "signature": b64(signature),
                "userHandle": b64(self.user_handle),
            },
        }


def with_passkey(user, rp_id: str = HOST, name: str = "Handy") -> SoftKey:
    key = SoftKey(rp_id, user)
    WebAuthn.add(user, name, key.register())
    user._has_mfa = None
    return key


@pytest.fixture(autouse=True)
def streng(settings):
    settings.MFA_STEP_UP = True


@pytest.fixture
def user():
    return make_user("karla@example.org")


def options(client: Client, url: str) -> dict:
    resp = client.get(url)
    assert resp.status_code == 200, resp.content
    return resp.json()["data"]["request_options"]


def test_passkeys_sind_eingeschaltet():
    assert passkeys.enabled()


def test_anmelden_ohne_passwort_zaehlt_als_zwei_faktor(user):
    key = with_passkey(user)
    client = Client()
    login_options = options(client, f"{AUTH}/auth/webauthn/login")
    # Ohne Passwort verlangt allauth die Entsperrung des Geräts
    assert login_options["publicKey"]["userVerification"] == "required"
    resp = client.post(
        f"{AUTH}/auth/webauthn/login",
        {"credential": key.sign(login_options)},
        content_type=JSON,
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["data"]["user"]["email"] == user.email
    # Gilt als frische Zwei-Faktor-Bestätigung (Nextcloud „nur mit 2FA“, MCP, heikle Aktionen)
    assert client.get("/api/me/confirm/").json() == {
        "step_up": "code",
        "fresh": True,
        "passkey": True,
    }
    request = client.get("/api/me/").wsgi_request
    assert "mfa" in session_auth(request)["amr"]


def test_ohne_geraete_entsperrung_keine_anmeldung(user):
    key = with_passkey(user)
    client = Client()
    login_options = options(client, f"{AUTH}/auth/webauthn/login")
    resp = client.post(
        f"{AUTH}/auth/webauthn/login",
        {"credential": key.sign(login_options, verified=False)},
        content_type=JSON,
    )
    assert resp.status_code == 400
    assert client.get("/api/me/").status_code in (401, 403)


def test_passkey_einer_anderen_adresse_gilt_hier_nicht(user):
    key = with_passkey(user, rp_id="verband.example")
    client = Client()
    login_options = options(client, f"{AUTH}/auth/webauthn/login")
    resp = client.post(
        f"{AUTH}/auth/webauthn/login",
        {"credential": key.sign(login_options)},
        content_type=JSON,
    )
    assert resp.status_code == 400
    assert client.get("/api/me/").status_code in (401, 403)


def test_passkey_als_zweiter_faktor_nach_dem_passwort(user):
    key = with_passkey(user)
    client = Client()
    resp = client.post(
        f"{AUTH}/auth/login", {"email": user.email, "password": PASSWORD}, content_type=JSON
    )
    assert resp.status_code == 401
    flow = next(f for f in resp.json()["data"]["flows"] if f.get("is_pending"))
    assert flow["id"] == "mfa_authenticate"
    assert "webauthn" in flow["types"]
    mfa_options = options(client, f"{AUTH}/auth/webauthn/authenticate")
    resp = client.post(
        f"{AUTH}/auth/webauthn/authenticate",
        {"credential": key.sign(mfa_options)},
        content_type=JSON,
    )
    assert resp.status_code == 200, resp.content
    assert client.get("/api/me/confirm/").json()["fresh"] is True


def test_heikle_aktion_mit_passkey_bestaetigen(user, api):
    key = with_passkey(user)
    client = api(user)
    # Ohne Bestätigung: 403 mit Hinweis, dass ein Passkey für diese Adresse da ist
    from rest_framework.request import Request
    from rest_framework.test import APIRequestFactory

    from accounts import step_up

    request = Request(APIRequestFactory().get("/", HTTP_HOST=HOST))
    request.user = user
    request._request.session = client.session
    with pytest.raises(step_up.StepUpRequired) as exc:
        step_up.require(request)
    assert exc.value.detail["passkey"] is True
    assert exc.value.detail["step_up"] == "code"

    assert client.get("/api/me/confirm/").json()["fresh"] is False
    reauth = options(client, f"{AUTH}/auth/webauthn/reauthenticate")
    resp = client.post(
        f"{AUTH}/auth/webauthn/reauthenticate",
        {"credential": key.sign(reauth)},
        content_type=JSON,
    )
    assert resp.status_code == 200, resp.content
    assert client.get("/api/me/confirm/").json()["fresh"] is True


def test_passkey_zaehlt_fuer_die_zwei_faktor_pflicht(user):
    assert has_mfa(user) is False
    with_passkey(user)
    assert has_mfa(user) is True


def test_liste_zeigt_adresse_je_passkey(user, api):
    with_passkey(user, name="Handy")
    with_passkey(user, rp_id="verband.example", name="Laptop")
    data = api(user).get("/api/me/passkeys/").json()
    assert data["enabled"] is True
    assert data["host"] == HOST
    rows = {row["name"]: row for row in data["passkeys"]}
    assert rows["Handy"]["host"] == HOST and rows["Handy"]["here"] is True
    assert rows["Handy"]["passwordless"] is True
    # Unbekannte Adresse: nicht anzeigen, aber auch nicht als „diese Adresse“
    assert rows["Laptop"]["here"] is False
    assert rows["Laptop"]["host"] in ("", "verband.example")
    assert "credential" not in json.dumps(data)


def test_name_der_einheit_fuer_handy_und_passwortmanager(settings, rf):
    from organizations.models import Organization

    platform = Organization.objects.filter(type=Organization.Type.PLATFORM).first()
    expected = (platform.display_name if platform else "") or settings.MFA_TOTP_ISSUER
    assert passkeys.rp_name(rf.get("/", HTTP_HOST=HOST)) == expected


def test_mail_bei_neuem_und_entferntem_passkey(user, django_capture_on_commit_callbacks):
    from allauth.mfa import signals

    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        with_passkey(user, name="Handy")
        item = Authenticator.objects.get(user=user, type=Authenticator.Type.WEBAUTHN)
        signals.authenticator_added.send(
            sender=Authenticator, request=None, user=user, authenticator=item
        )
        signals.authenticator_removed.send(
            sender=Authenticator, request=None, user=user, authenticator=item
        )
    subjects = [m.subject for m in mail.outbox]
    assert "Neuer Passkey für dein Konto" in subjects
    assert "Passkey entfernt" in subjects
    assert all(m.to == [user.email] for m in mail.outbox)
    assert "„Handy“" in mail.outbox[0].body


def test_abschalten(settings, user, api):
    settings.MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
    assert passkeys.enabled() is False
    with_passkey(user)
    assert api(user).get("/api/me/passkeys/").json()["enabled"] is False
    assert api(user).get("/api/me/confirm/").json()["passkey"] is False


def test_verbund_bietet_passkey_an(user, api, monkeypatch):
    from peering import sso

    with_passkey(user)

    def zu_alt(*args, **kwargs):
        raise sso.ReauthRequired(True)

    monkeypatch.setattr(sso, "issue", zu_alt)
    resp = api(user).post(
        "/api/peering/sso/issue/",
        {"rp": "x", "state": "y", "purpose": "login"},
        content_type=JSON,
    )
    assert resp.status_code == 409
    assert resp.json()["passkey"] is True and resp.json()["needs_code"] is True
