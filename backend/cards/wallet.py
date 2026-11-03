"""Optionale Google-Wallet-Ausgabe; Anbieter-Referenzen getrennt vom QR-Schlüssel.

Apple nutzt einen eigenen Dateiexport. Referenzen sind je Anbieter unter wallet_passes
getrennt. Alte Google-Objekte werden niemals mit einem neuen QR-Schlüssel versorgt.
"""

import base64
import hashlib
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from django.conf import settings
from django.db import transaction

from .models import MemberCard

API = "https://walletobjects.googleapis.com/walletobjects/v1/"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 -- öffentlicher OAuth-Endpunkt
SCOPE = "https://www.googleapis.com/auth/wallet_object.issuer"


class WalletError(Exception):
    """Konfiguration oder Anbieter vorübergehend nicht verfügbar (keine Geheimnisse)."""


def enabled():
    return bool(settings.GOOGLE_WALLET_ISSUER_ID and settings.GOOGLE_WALLET_CREDENTIALS_FILE)


def _b64(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class GoogleWallet:
    def __init__(self):
        if not enabled():
            raise WalletError("Google Wallet ist nicht eingerichtet.")
        try:
            credentials = json.loads(Path(settings.GOOGLE_WALLET_CREDENTIALS_FILE).read_text())
            self.email = credentials["client_email"]
            self.key = serialization.load_pem_private_key(
                credentials["private_key"].encode(), password=None
            )
            if not isinstance(self.key, rsa.RSAPrivateKey):
                raise ValueError("RSA required")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise WalletError("Google-Wallet-Zugangsdaten sind nicht verfügbar.") from exc
        self.issuer = settings.GOOGLE_WALLET_ISSUER_ID
        self.class_id = f"{self.issuer}.hubiplan_membership"
        self.access_token = None

    def sign(self, claims):
        parts = [
            _b64(json.dumps(v, separators=(",", ":")).encode())
            for v in ({"alg": "RS256", "typ": "JWT"}, claims)
        ]
        unsigned = ".".join(parts).encode()
        signature = self.key.sign(unsigned, padding.PKCS1v15(), hashes.SHA256())
        return unsigned.decode() + "." + _b64(signature)

    def _request(self, url, method, data, headers=None, allowed=()):
        request = Request(url, data=data, headers=headers or {}, method=method)  # noqa: S310
        try:
            with urlopen(request, timeout=10) as response:  # noqa: S310 -- feste Google-URLs
                return json.load(response)
        except HTTPError as exc:
            if exc.code in allowed:
                return None
            raise WalletError(f"Google Wallet antwortet mit HTTP {exc.code}.") from exc
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            raise WalletError("Google Wallet ist gerade nicht erreichbar.") from exc

    def request(self, method, resource, data, allowed=()):
        if not self.access_token:
            now = int(time.time())
            assertion = self.sign(
                {
                    "iss": self.email,
                    "scope": SCOPE,
                    "aud": TOKEN_URL,
                    "iat": now,
                    "exp": now + 3600,
                }
            )
            token = self._request(
                TOKEN_URL,
                "POST",
                urlencode(
                    {
                        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                        "assertion": assertion,
                    }
                ).encode(),
                {"Content-Type": "application/x-www-form-urlencoded"},
            )
            try:
                self.access_token = token["access_token"]
            except (KeyError, TypeError) as exc:
                raise WalletError("Google-Wallet-Anmeldung fehlgeschlagen.") from exc
        return self._request(
            API + resource,
            method,
            json.dumps(data).encode(),
            {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            allowed,
        )

    def object_id(self, card):
        # Frontend-Adresse trennt auch mehrere Installationen desselben Ausstellers.
        version = hashlib.sha256(card.url.encode()).hexdigest()
        return f"{self.issuer}.hubiplan_{version}"

    def payload(self, card):
        def text(value):
            return {"defaultValue": {"language": "de", "value": value}}

        person = card.membership.person
        result = {
            "id": self.object_id(card),
            "classId": self.class_id,
            "state": "ACTIVE",
            "cardTitle": text(card.organization.name),
            "header": text(f"{person.first_name} {person.last_name}".strip()),
            "subheader": text("Mitgliedsausweis"),
            "barcode": {"type": "QR_CODE", "value": card.url},
            "textModulesData": [
                {
                    "id": "verification",
                    "header": "Mitgliedschaft prüfen",
                    "body": "Bitte QR-Code scannen. Die aktuelle Gültigkeit wird online geprüft.",
                }
            ],
        }
        # Nur ein öffentliches Vereinslogo; niemals Mitgliederfotos übertragen.
        if settings.GOOGLE_WALLET_LOGO_URL:
            result["logo"] = {"sourceUri": {"uri": settings.GOOGLE_WALLET_LOGO_URL}}
        return result

    def save_url(self, object_id):
        origin = urlsplit(settings.FRONTEND_URL)
        token = self.sign(
            {
                "iss": self.email,
                "aud": "google",
                "typ": "savetowallet",
                "iat": int(time.time()),
                "origins": [origin.netloc],
                # Nur Referenz: ein alter Speicherlink kann kein Objekt reaktivieren.
                "payload": {"genericObjects": [{"id": object_id}]},
            }
        )
        return "https://pay.google.com/gp/v/save/" + token


def _fingerprint(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def issue_google(card_id):
    client = GoogleWallet()
    with transaction.atomic():
        card = (
            MemberCard.objects.select_for_update()
            .select_related("membership__person", "organization")
            .get(pk=card_id)
        )
        if (
            card.revoked_at
            or card.membership.purged_at
            or not card.organization.is_active
            or not card.membership.current_period()
        ):
            raise WalletError("Für diese Mitgliedschaft ist kein gültiger Ausweis verfügbar.")
        payload = client.payload(card)
        # Vor der Netzübertragung merken: ein späterer Fehler bleibt abgleichbar.
        refs = dict(card.wallet_passes)
        google = dict(refs.get("google", {}))
        google.setdefault(payload["id"], "")
        refs["google"] = google
        card.wallet_passes = refs
        card.save(update_fields=["wallet_passes"])
    client.request("POST", "genericClass", {"id": client.class_id}, allowed=(409,))
    client.request("POST", "genericObject", payload, allowed=(409,))
    # Auch bestehende Objekte auf den aktuellen Stand bringen.
    sync_google(card.pk, client)
    return client.save_url(payload["id"])


def sync_google(card_id, client=None):
    client = client or GoogleWallet()
    with transaction.atomic():
        card = (
            MemberCard.objects.select_for_update()
            .select_related("membership__person", "organization")
            .get(pk=card_id)
        )
        refs = dict(card.wallet_passes)
        google = dict(refs.get("google", {}))
        active = (
            not card.revoked_at
            and not card.membership.purged_at
            and card.organization.is_active
            and card.membership.current_period()
        )
        current_id = client.object_id(card)
        for object_id, previous in google.items():
            if not object_id.startswith(client.issuer + "."):
                continue
            if active and object_id == current_id:
                payload = client.payload(card)
            else:
                payload = {
                    "state": "INACTIVE",
                    "header": {"defaultValue": {"language": "de", "value": "Ungültiger Ausweis"}},
                }
            fingerprint = _fingerprint(payload)
            if fingerprint != previous:
                response = client.request(
                    "PATCH", "genericObject/" + object_id, payload, allowed=(404,)
                )
                if response is not None:
                    google[object_id] = fingerprint
        refs["google"] = google
        card.wallet_passes = refs
        card.save(update_fields=["wallet_passes"])
