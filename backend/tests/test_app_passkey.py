"""Anmeldung der App mit Passkey (devices/passkey.py, docs/app.md). Erfundene Daten.

Der Software-Passkey aus ``test_passkeys`` spielt das Telefon: Die Android-App unterschreibt
mit der Herkunft ``android:apk-key-hash:…``, die iOS-App mit ``https://<Adresse>``.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

import base64
import hashlib

import pytest
from django.test import Client

from devices.models import Device

from .test_app_devices import APP, app, member  # noqa: F401  (Fixtures)
from .test_m12_events import JSON, cal, org_base  # noqa: F401  (Fixtures)
from .test_passkeys import with_passkey

pytestmark = pytest.mark.django_db

# Erfundener Signatur-Fingerabdruck (kein echtes Zertifikat)
FINGERPRINT = ":".join(["AB"] * 16 + ["CD"] * 16)
ANDROID_ORIGIN = (
    "android:apk-key-hash:"
    + base64.urlsafe_b64encode(bytes.fromhex(FINGERPRINT.replace(":", ""))).rstrip(b"=").decode()
)
IOS_APP = "ABCDE12345.de.hubiplan.app"


@pytest.fixture
def apps(settings):
    settings.APP_ANDROID_FINGERPRINTS = [FINGERPRINT.lower()]
    settings.APP_IOS_APP_IDS = [IOS_APP]
    return settings


def begin(client: Client | None = None) -> dict:
    resp = (client or Client()).post(f"{APP}passkey/begin/")
    assert resp.status_code == 200, resp.content
    return resp.json()


def login(start: dict, credential: dict, name: str = "Pixel 8"):
    return Client().post(
        f"{APP}passkey/",
        {
            "challenge_id": start["challenge_id"],
            "credential": credential,
            "name": name,
            "platform": "android",
            "app_version": "47",
        },
        content_type=JSON,
    )


class TestWellKnown:
    def test_ohne_apps_nichts(self):
        assert Client().get("/.well-known/assetlinks.json").status_code == 404
        assert Client().get("/.well-known/apple-app-site-association").status_code == 404
        assert Client().get(f"{APP}instance/").json()["passkey"] == []

    def test_assetlinks_fuer_android(self, apps):
        resp = Client().get("/.well-known/assetlinks.json")
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/json"
        [entry] = resp.json()
        assert entry["relation"] == ["delegate_permission/common.get_login_creds"]
        assert entry["target"] == {
            "namespace": "android_app",
            "package_name": "de.hubiplan.app",
            "sha256_cert_fingerprints": [FINGERPRINT],
        }

    def test_apple_app_site_association(self, apps):
        resp = Client().get("/.well-known/apple-app-site-association")
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/json"
        assert resp.json() == {"webcredentials": {"apps": [IOS_APP]}}

    def test_ungueltige_werte_fallen_weg(self, settings):
        settings.APP_ANDROID_FINGERPRINTS = ["zu-kurz"]
        settings.APP_IOS_APP_IDS = ["de.hubiplan.app"]
        assert Client().get("/.well-known/assetlinks.json").status_code == 404
        assert Client().get("/.well-known/apple-app-site-association").status_code == 404

    def test_instanz_nennt_plattformen(self, apps):
        data = Client().get(f"{APP}instance/").json()
        assert data["passkey"] == ["android", "ios"]
        assert "app-passkey" in data["features"]

    def test_passkeys_aus(self, apps):
        apps.MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
        assert Client().get("/.well-known/assetlinks.json").status_code == 404
        assert Client().get(f"{APP}instance/").json()["passkey"] == []
        assert Client().post(f"{APP}passkey/begin/").status_code == 404


class TestAnmelden:
    def test_android_app(self, apps, member):
        user, _ = member
        key = with_passkey(user)
        key.origin = ANDROID_ORIGIN
        start = begin()
        assert start["options"]["rpId"] == "testserver"
        # Ohne Passwort muss das Telefon entsperrt werden
        assert start["options"]["userVerification"] == "required"
        resp = login(start, key.sign(start["options"]))
        assert resp.status_code == 201, resp.json()
        data = resp.json()
        assert data["token"].startswith("hpd_")
        assert data["user"]["email"] == user.email
        assert app(data["token"]).get(f"{APP}me/").status_code == 200
        device = Device.objects.get()
        assert device.name == "Pixel 8" and device.platform == "android"
        # Zuletzt benutzt wird vermerkt
        from accounts.passkeys import passkeys

        assert passkeys(user).get().last_used_at is not None

    def test_ios_app(self, apps, member):
        user, _ = member
        key = with_passkey(user)  # Herkunft https://testserver
        start = begin()
        resp = login(start, key.sign(start["options"]), name="iPhone")
        assert resp.status_code == 201, resp.json()

    def test_aufgabe_nur_einmal(self, apps, member):
        user, _ = member
        key = with_passkey(user)
        key.origin = ANDROID_ORIGIN
        start = begin()
        assert login(start, key.sign(start["options"])).status_code == 201
        resp = login(start, key.sign(start["options"]))
        assert resp.status_code == 400
        assert Device.objects.count() == 1

    def test_fremde_app_abgewiesen(self, apps, member):
        user, _ = member
        key = with_passkey(user)
        other = hashlib.sha256(b"andere App").digest()
        key.origin = "android:apk-key-hash:" + base64.urlsafe_b64encode(other).rstrip(b"=").decode()
        start = begin()
        assert login(start, key.sign(start["options"])).status_code == 400
        assert not Device.objects.exists()

    def test_fremde_webseite_abgewiesen(self, apps, member):
        user, _ = member
        key = with_passkey(user)
        key.origin = "https://boese.example"
        start = begin()
        assert login(start, key.sign(start["options"])).status_code == 400

    def test_ohne_entsperren_keine_anmeldung(self, apps, member):
        user, _ = member
        key = with_passkey(user)
        key.origin = ANDROID_ORIGIN
        start = begin()
        assert login(start, key.sign(start["options"], verified=False)).status_code == 400
        assert not Device.objects.exists()

    def test_passkey_einer_anderen_adresse(self, apps, member):
        user, _ = member
        key = with_passkey(user, rp_id="verband.example")
        key.origin = ANDROID_ORIGIN
        start = begin()
        assert login(start, key.sign(start["options"])).status_code == 400

    def test_gesperrtes_konto(self, apps, member):
        user, _ = member
        key = with_passkey(user)
        key.origin = ANDROID_ORIGIN
        user.is_active = False
        user.save(update_fields=["is_active"])
        start = begin()
        assert login(start, key.sign(start["options"])).status_code == 400

    def test_ohne_mitgliederbereich(self, apps):
        from .factories import make_user

        user = make_user("ohne-bereich@example.org")
        key = with_passkey(user)
        key.origin = ANDROID_ORIGIN
        start = begin()
        assert login(start, key.sign(start["options"])).status_code == 403
        assert not Device.objects.exists()

    def test_unsinnige_antwort(self, apps):
        start = begin()
        assert login(start, {"id": "x", "response": {}}).status_code == 400


class TestVerwaltungFreischalten:
    """Verwaltung in der App wahlweise mit Passkey statt Passwort und Code."""

    def _device(self, user):
        key = with_passkey(user)
        key.origin = ANDROID_ORIGIN
        start = begin()
        resp = login(start, key.sign(start["options"]))
        assert resp.status_code == 201, resp.json()
        return key, resp.json()["token"]

    def _unlock(self, token, key):
        start = begin()
        return app(token).post(
            f"{APP}admin/unlock/",
            {
                "passkey_challenge_id": start["challenge_id"],
                "passkey_credential": key.sign(start["options"]),
            },
            content_type=JSON,
        )

    def test_mit_passkey_ohne_totp(self, apps, cal, member):
        from .factories import give_role

        user, _ = member
        give_role(user, cal["a"])
        key, token = self._device(user)
        overview = app(token).get(f"{APP}admin/").json()
        assert overview["passkey"] is True and overview["two_factor"] is False
        resp = self._unlock(token, key)
        assert resp.status_code == 201, resp.json()
        assert app(resp.json()["token"]).get(f"{APP}admin/").status_code == 200

    def test_passkey_eines_anderen_kontos(self, apps, cal, member):
        from .factories import give_role, make_user

        user, _ = member
        give_role(user, cal["a"])
        _, token = self._device(user)
        other = make_user("fremd@example.org")
        foreign = with_passkey(other)
        foreign.origin = ANDROID_ORIGIN
        assert self._unlock(token, foreign).status_code == 400
        assert not Device.objects.get(user=user).admin_token_hash

    def test_ohne_totp_und_ohne_passkey_weiter_der_hinweis(self, apps, cal, member):
        from .factories import give_role

        user, _ = member
        give_role(user, cal["a"])
        _, token = self._device(user)
        resp = app(token).post(
            f"{APP}admin/unlock/", {"password": "x", "code": "123456"}, content_type=JSON
        )
        assert resp.status_code == 400
        assert "Zwei-Faktor" in resp.json()["detail"]
