"""2FA-Geheimnisse (TOTP-Schlüssel, Saat der Wiederherstellungscodes) verschlüsselt speichern.

allauth legt diese Geheimnisse in ``mfa_authenticator.data`` ab und ruft dafür
``encrypt``/``decrypt`` des Adapters auf. Verschlüsselt wird mit Fernet und einem
eigenen Schlüssel aus der Server-``.env`` (``MFA_ENCRYPTION_KEY``). Er liegt nicht in
der Datenbank und nicht im Backup: Wer nur einen Datenbank-Dump hat, kann damit keine
2FA-Codes erzeugen.

Mehrere Schlüssel (``MFA_ENCRYPTION_KEYS=neu,alt``) erlauben einen Wechsel: verschlüsselt
wird mit dem ersten, entschlüsselt mit jedem.
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote

from allauth.mfa.adapter import DefaultMFAAdapter
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

PREFIX = "enc1:"


@lru_cache(maxsize=4)
def _fernet(keys: tuple[str, ...]) -> MultiFernet:
    if not keys:
        raise ImproperlyConfigured("MFA_ENCRYPTION_KEY muss gesetzt sein.")
    try:
        return MultiFernet([Fernet(key.encode()) for key in keys])
    except ValueError as exc:
        raise ImproperlyConfigured(
            "MFA_ENCRYPTION_KEY ist kein gültiger Schlüssel (32 Byte, URL-sicheres Base64)."
        ) from exc


def fernet() -> MultiFernet:
    return _fernet(tuple(settings.MFA_ENCRYPTION_KEYS))


def is_encrypted(value: str) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def encrypt(text: str) -> str:
    if is_encrypted(text):
        return text
    return PREFIX + fernet().encrypt(text.encode()).decode()


def decrypt(value: str) -> str:
    if not is_encrypted(value):
        # Die Migration hat alle Einträge verschlüsselt; Klartext gilt als untergeschoben
        raise ImproperlyConfigured("2FA-Geheimnis ist nicht verschlüsselt gespeichert.")
    try:
        return fernet().decrypt(value[len(PREFIX) :].encode()).decode()
    except InvalidToken as exc:
        raise ImproperlyConfigured(
            "2FA-Geheimnis lässt sich nicht entschlüsseln: falscher MFA_ENCRYPTION_KEY?"
        ) from exc


def rotate(value: str) -> str:
    """Mit dem ersten (neuen) Schlüssel neu verschlüsseln."""
    if not is_encrypted(value):
        return encrypt(value)
    return PREFIX + fernet().rotate(value[len(PREFIX) :].encode()).decode()


# Felder in Authenticator.data, die Geheimnisse enthalten
def transform_data(kind: str, data: dict, func) -> dict:
    data = dict(data or {})
    if kind == "totp" and data.get("secret"):
        data["secret"] = func(data["secret"])
    if kind == "recovery_codes":
        if data.get("seed"):
            data["seed"] = func(data["seed"])
        if isinstance(data.get("migrated_codes"), list):
            data["migrated_codes"] = [func(code) for code in data["migrated_codes"]]
    return data


class MFAAdapter(DefaultMFAAdapter):
    def encrypt(self, text: str) -> str:
        return encrypt(text)

    def decrypt(self, encrypted_text: str) -> str:
        return decrypt(encrypted_text)

    def build_totp_url(self, user, secret: str) -> str:
        url = super().build_totp_url(user, secret)
        image = totp_image_url(user, getattr(self, "request", None))
        if image:
            # Inoffiziell (FreeOTP u. a.); Apps ohne Unterstützung übergehen den Parameter
            url += "&image=" + quote(image, safe="")
        return url

    def get_public_key_credential_rp_entity(self) -> dict[str, str]:
        """Passkeys gelten für die aufgerufene Adresse; Name der Einheit dieser Adresse."""
        from allauth.core import context

        from .passkeys import current_host, rp_name

        request = context.request
        return {"id": current_host(request), "name": rp_name(request)}


def totp_image_url(user, request=None) -> str:
    """Absolute https-Adresse des Vereinslogos für den QR-Code der 2FA-Einrichtung.

    Einige Authenticator-Apps (z. B. FreeOTP) zeigen das Bild aus dem inoffiziellen
    ``image``-Parameter der otpauth-Adresse als Symbol. Welches Logo: das der Einheit, deren
    Adresse aufgerufen ist; sonst das des einzigen Vereins (bzw. Dachverbands), in dem das
    Konto Rollen hat; sonst das der Plattform (White Label). Ohne Logo oder ohne https: leer.
    """
    from urllib.parse import urljoin

    from access.permissions import organizations_for
    from core.tenancy import user_view
    from organizations.addresses import base_url, request_unit
    from organizations.models import Organization
    from organizations.theme import effective_theme

    unit = request_unit(request) if request is not None else None
    if unit is None:
        with user_view(user.pk):
            orgs = [org for org, _ in organizations_for(user)]
        clubs, federations = set(), set()
        for org in orgs:
            for item in org.ancestors():
                if item.type == Organization.Type.CLUB:
                    clubs.add(item)
                    break
                if item.type == Organization.Type.FEDERATION:
                    federations.add(item)
                    break
        if len(clubs) == 1:
            unit = clubs.pop()
        elif not clubs and len(federations) == 1:
            unit = federations.pop()
    if unit is not None:
        chain = unit.ancestors()
    else:
        chain = list(Organization.objects.filter(type=Organization.Type.PLATFORM)[:1])
    logo = effective_theme(chain)["logo_url"] if chain else None
    if not logo:
        return ""
    url = urljoin(base_url(unit).rstrip("/") + "/", logo)
    return url if url.startswith("https://") else ""
