"""Bekannte Geräte: Die Kontosperre nach Fehlversuchen trifft nur fremde Geräte.

Fünf falsche Passwörter in fünf Minuten sperren die Passwort-Anmeldung eines Kontos
(allauth, ``login_failed``). Wer die E-Mail-Adresse kennt, konnte den Inhaber so von außen
aussperren (Gesamtaudit 11.11. S-03). Nach einer erfolgreichen Anmeldung bekommt der Browser
deshalb ein signiertes Cookie; Anmeldungen mit diesem Cookie zählen in einem eigenen Zähler
je Gerät (Muster „Device Cookies“ von OWASP). Die Sperre gegen verteiltes Durchprobieren
bleibt für alle anderen bestehen, und auch ein gestohlenes Cookie erlaubt nicht mehr Versuche
als bisher.
"""

from __future__ import annotations

import logging
import secrets

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.utils.crypto import salted_hmac

COOKIE = "hp_geraet"
MAX_AGE = 180 * 24 * 60 * 60
MAX_ACCOUNTS = 8
MAIL_PAUSE = 6 * 60 * 60
_SALT = "accounts.known-device"
_ATTR = "_known_device_email"

log = logging.getLogger(__name__)


def _account(email: str) -> str:
    return salted_hmac(_SALT, (email or "").strip().lower()).hexdigest()[:32]


def _read(request) -> dict:
    raw = request.COOKIES.get(COOKIE)
    if not raw:
        return {}
    try:
        data = signing.loads(raw, salt=_SALT, max_age=MAX_AGE)
    except signing.BadSignature:
        return {}
    if not isinstance(data, dict) or not isinstance(data.get("a"), list) or not data.get("i"):
        return {}
    return data


def device_for(request, email: str) -> str | None:
    """Kennung des Geräts, wenn sich dieses Konto hier schon erfolgreich angemeldet hat."""
    data = _read(request)
    if email and _account(email) in data.get("a", []):
        return str(data["i"])
    return None


def remember(sender=None, request=None, user=None, **kwargs) -> None:
    """Nach erfolgreicher Anmeldung (auch mit zweitem Faktor): Gerät für das Konto merken."""
    email = getattr(user, "email", "")
    if request is not None and email:
        setattr(request, _ATTR, email)


class KnownDeviceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        email = getattr(request, _ATTR, "")
        if email:
            data = _read(request) or {"i": secrets.token_urlsafe(16), "a": []}
            account = _account(email)
            accounts = [a for a in data["a"] if a != account] + [account]
            data["a"] = accounts[-MAX_ACCOUNTS:]
            response.set_cookie(
                COOKIE,
                signing.dumps(data, salt=_SALT, compress=True),
                max_age=MAX_AGE,
                httponly=True,
                secure=settings.SESSION_COOKIE_SECURE,
                samesite="Lax",
            )
        return response


def notify_locked(email: str) -> None:
    """Dem Inhaber sagen, dass sein Konto für fremde Geräte gesperrt wurde (selten)."""
    from django.utils.translation import gettext as _

    from core.i18n import language_of, user_language
    from core.tenancy import rls_bypass

    from .models import User

    if not email or not cache.add(f"login-locked-mail:{_account(email)}", 1, MAIL_PAUSE):
        return
    with rls_bypass():
        user = User.objects.filter(email__iexact=email.strip(), is_active=True).first()
    if user is None:
        return
    try:
        from outbox.mail import send

        with language_of(user):
            subject = _("Zu viele Fehlversuche bei der Anmeldung")
            body = _(
                "Hallo {name},\n\nfür dein Konto wurde mehrmals hintereinander ein falsches "
                "Passwort eingegeben. Die Anmeldung mit Passwort ist deshalb für einige "
                "Minuten gesperrt, allerdings nur auf fremden Geräten.\n\n"
                "Auf Geräten, mit denen du dich schon einmal angemeldet hast, und mit einem "
                "Passkey kannst du dich weiter anmelden. Dein Passwort wurde nicht erraten; "
                "du musst nichts tun.\n\n"
                "Warst du das selbst und hast das Passwort vergessen, kannst du auf der "
                "Anmeldeseite ein neues anfordern: {link}\n"
            ).format(
                name=user.get_full_name() or user.email,
                link=f"{settings.FRONTEND_URL}/anmelden",
            )
        send(
            [user.email],
            subject,
            body,
            kind="sicherheit",
            fail_silently=True,
            language=user_language(user),
        )
    except Exception:  # noqa: BLE001 – eine Mail darf die Antwort nie verhindern
        log.exception("Hinweis auf gesperrte Anmeldung nicht gesendet")


def connect() -> None:
    from django.contrib.auth.signals import user_logged_in

    user_logged_in.connect(remember, dispatch_uid="known-device-remember")
