"""Anmeldung der App mit Passkey (docs/app.md, „Passkey“).

Die App fragt ``POST /api/app/v1/passkey/begin/`` nach einer Aufgabe (WebAuthn
„challenge“), lässt das Telefon den Passkey dieser Adresse wählen und schickt die Antwort an
``POST /api/app/v1/passkey/``. Stimmt sie, gibt es wie beim QR-Code sofort einen
Geräteschlüssel; eine Sitzung entsteht dabei nicht.

Ein Passkey gilt für genau eine Adresse (Relying Party ID, siehe ``accounts/passkeys.py``).
Damit Android ihn einer App überhaupt anbietet, bestätigt die Instanz unter
``/.well-known/assetlinks.json``, welche Apps das dürfen. Android-Apps unterschreiben mit der
Herkunft ``android:apk-key-hash:<SHA-256 des Signaturzertifikats>``.

iOS gibt Passkeys nur für Adressen heraus, die beim Bauen fest in der App stehen; für selbst
betriebene Instanzen geht das nicht. Die iOS-App meldet sich deshalb im eingebetteten Browser
an (``/app/anmelden``, dort gilt der Passkey wie auf der Webseite) und verbindet sich über den
Einmalcode wie beim QR-Code.
"""

from __future__ import annotations

import base64
import logging
import re
import secrets
from urllib.parse import urlsplit

from allauth.account.utils import url_str_to_user_pk
from allauth.mfa.models import Authenticator
from allauth.mfa.webauthn.internal import auth as webauthn_auth
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.http import Http404, JsonResponse
from django.utils.translation import gettext
from django.views.decorators.http import require_GET
from fido2.rpid import verify_rp_id
from fido2.server import Fido2Server
from fido2.utils import websafe_decode
from fido2.webauthn import (
    AuthenticationResponse,
    PublicKeyCredentialRpEntity,
    UserVerificationRequirement,
)
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import passkeys
from core.tenancy import set_rls
from portal import services as portal_services

from .views import DeviceSerializer, _create_device, _limit, _paired

logger = logging.getLogger(__name__)

# Die offizielle Android-App. Die Fingerabdrücke der Signaturzertifikate sind öffentlich, keine
# Geheimnisse. Eigene Builds ergänzen sie in der .env (HUBIPLAN_APP_ANDROID_FINGERPRINTS,
# docs/betrieb.md).
OFFICIAL_ANDROID_FINGERPRINTS: tuple[str, ...] = (
    # Google Play, App-Signaturschlüssel
    "93:60:51:21:C6:33:6A:CB:63:47:58:72:5D:0C:4B:7A:FC:79:9D:C2:47:C1:06:9F:D1:AE:64:1A:14:1E:D2:21",
    # Uploadschlüssel des Herausgebers (selbst signierte APKs, Variante foss)
    "EE:82:1A:56:59:E4:5D:D8:96:50:0E:D5:63:04:0F:1A:6A:1D:2A:C7:9E:09:A6:04:97:B4:8B:A9:1D:D2:45:00",
)

CHALLENGE_SECONDS = 5 * 60
_HEX = re.compile(r"^[0-9A-F]{64}$")


def _normalize_fingerprint(value: str) -> str:
    """``ab:cd:…`` oder ``ABCD…`` → ``AB:CD:…``; ungültig: leer."""
    raw = value.replace(":", "").replace(" ", "").upper()
    if not _HEX.match(raw):
        return ""
    return ":".join(raw[i : i + 2] for i in range(0, 64, 2))


def android_fingerprints() -> list[str]:
    result: list[str] = []
    for value in (*OFFICIAL_ANDROID_FINGERPRINTS, *settings.APP_ANDROID_FINGERPRINTS):
        normal = _normalize_fingerprint(value)
        if not normal:
            logger.warning("Ungültiger Android-Fingerabdruck in HUBIPLAN_APP_ANDROID_FINGERPRINTS")
        elif normal not in result:
            result.append(normal)
    return result


def android_origins() -> set[str]:
    """Herkunft, mit der Android-Apps ihre Passkey-Antworten unterschreiben."""
    origins = set()
    for fingerprint in android_fingerprints():
        digest = bytes.fromhex(fingerprint.replace(":", ""))
        origins.add(
            "android:apk-key-hash:" + base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        )
    return origins


# --- /.well-known/ ---


@require_GET
def assetlinks(request):
    """Android: Diese Apps dürfen Passkeys dieser Adresse nutzen."""
    fingerprints = android_fingerprints()
    if not passkeys.enabled() or not fingerprints:
        raise Http404
    return JsonResponse(
        [
            {
                "relation": ["delegate_permission/common.get_login_creds"],
                "target": {
                    "namespace": "android_app",
                    "package_name": settings.APP_ANDROID_PACKAGE,
                    "sha256_cert_fingerprints": fingerprints,
                },
            }
        ],
        safe=False,
    )


# --- Anmeldung ---


def _server(request) -> Fido2Server:
    host = passkeys.current_host(request)
    rp = PublicKeyCredentialRpEntity(id=host, name=passkeys.rp_name(request))
    apps = android_origins()

    insecure = getattr(settings, "MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN", False)

    def verify_origin(origin: str) -> bool:
        if origin in apps or verify_rp_id(host, origin):
            return True
        # Entwicklung (DJANGO_DEBUG): auch http, aber nur die eigene Adresse, nie fremde Apps
        if insecure:
            parts = urlsplit(origin)
            return parts.scheme == "http" and parts.hostname == host
        return False

    return Fido2Server(rp, verify_origin=verify_origin)


def _cache_key(challenge_id: str) -> str:
    return f"app:passkey:{challenge_id}"


def _failed():
    return ValidationError(
        {"detail": gettext("Der Passkey wurde nicht erkannt. Bitte noch einmal versuchen.")},
        code="passkey_failed",
    )


class PasskeyBeginView(APIView):
    """App: Aufgabe für die Anmeldung mit Passkey (5 Minuten, einmal nutzbar)."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request):
        _limit(request, "passkey-begin")
        host = passkeys.current_host(request)
        if not passkeys.enabled() or not host:
            raise NotFound(gettext("Passkeys sind auf dieser Instanz ausgeschaltet."))
        options, state = _server(request).authenticate_begin(
            user_verification=UserVerificationRequirement.REQUIRED
        )
        challenge_id = secrets.token_urlsafe(24)
        cache.set(_cache_key(challenge_id), {"state": state, "host": host}, CHALLENGE_SECONDS)
        return Response(
            {
                "challenge_id": challenge_id,
                # Wie navigator.credentials.get({publicKey}) im Browser (WebAuthn-JSON)
                "options": dict(options)["publicKey"],
                "expires_in": CHALLENGE_SECONDS,
            }
        )


def verify(request, challenge_id: str, credential, user=None):
    """Antwort eines Passkeys auf eine Aufgabe aus ``passkey/begin/`` prüfen.

    Gibt (Konto, Passkey) zurück. Mit ``user`` muss der Passkey zu diesem Konto gehören
    (Freischalten der Verwaltung); sonst ergibt sich das Konto aus dem Passkey.
    """
    key = _cache_key(str(challenge_id))
    entry = cache.get(key)
    # Einmal nutzbar: Wer sie zuerst löscht, darf weiter
    if not entry or not cache.delete(key):
        raise ValidationError(
            {"detail": gettext("Die Anmeldung ist abgelaufen. Bitte noch einmal versuchen.")},
            code="passkey_expired",
        )
    if entry.get("host") != passkeys.current_host(request) or not isinstance(credential, dict):
        raise _failed()
    try:
        response = AuthenticationResponse.from_dict(credential)
        handle = credential.get("response", {}).get("userHandle")
        user_pk = url_str_to_user_pk(websafe_decode(handle).decode("utf8"))
    except (TypeError, ValueError, KeyError, AttributeError):
        raise _failed() from None
    if user is None:
        set_rls(None, user_pk)
        user = get_user_model().objects.filter(pk=user_pk, is_active=True).first()
    elif str(user.pk) != str(user_pk):
        user = None
    if user is None:
        raise _failed()
    try:
        binding = _server(request).authenticate_complete(
            entry["state"], webauthn_auth.get_credentials(user), response
        )
    except (TypeError, ValueError, KeyError):
        raise _failed() from None
    authenticator = webauthn_auth.get_authenticator_by_credential_id(user, binding.credential_id)
    if authenticator is None or authenticator.type != Authenticator.Type.WEBAUTHN:
        raise _failed()
    return user, authenticator


class PasskeyLoginSerializer(DeviceSerializer):
    challenge_id = serializers.CharField(max_length=100)
    credential = serializers.JSONField()


class PasskeyLoginView(APIView):
    """App: Antwort des Passkeys prüfen und Geräteschlüssel ausgeben."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request):
        _limit(request, "passkey")
        data = PasskeyLoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        user, authenticator = verify(request, v["challenge_id"], v["credential"])
        if not portal_services.portal_accesses(user):
            raise PermissionDenied(
                gettext("Für dieses Konto ist kein Mitgliederbereich freigeschaltet.")
            )
        with transaction.atomic():
            authenticator.record_usage()
            device, token = _create_device(user, v)
        return _paired(user, device, token)
