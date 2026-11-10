"""Frischer zweiter Faktor für heikle Aktionen (Gesamtaudit 10.11., Frage 1).

Vollständige Exporte, Rollen vergeben, die App koppeln und endgültiges Löschen verlangen
einen Code aus der Authenticator-App, der höchstens ``FRESH_SECONDS`` alt ist (auch der
Code bei der Anmeldung zählt). Konten, die die Zwei-Faktor-Anmeldung noch nicht
eingerichtet haben (Übergangsfrist für Vorstand und Kasse), bestätigen stattdessen mit
ihrem Passwort.

Ist die Bestätigung zu alt, antwortet der Server mit 403 und ``step_up`` (``code`` oder
``password``); die Oberfläche fragt dann nach und sendet die Anfrage erneut.
"""

from __future__ import annotations

import time

from django.conf import settings
from django.utils.translation import gettext
from rest_framework import status
from rest_framework.exceptions import APIException, PermissionDenied, Throttled
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.ratelimit import too_many

from .mfa_policy import has_mfa

FRESH_SECONDS = 10 * 60
# Fehlversuche beim Bestätigen: 10 je 15 Minuten und Konto
RATE = (10, 15 * 60)


class StepUpRequired(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "step_up"

    def __init__(self, needs: str):
        message = (
            gettext("Bitte zur Sicherheit einen aktuellen Code aus der Authenticator-App eingeben.")
            if needs == "code"
            else gettext("Bitte zur Sicherheit dein Passwort eingeben.")
        )
        super().__init__({"detail": message, "step_up": needs})


def _records(request) -> list[dict]:
    from allauth.account.internal.flows.login import AUTHENTICATION_METHODS_SESSION_KEY

    session = getattr(request, "session", None)
    if session is None:
        return []
    return [r for r in session.get(AUTHENTICATION_METHODS_SESSION_KEY, []) if isinstance(r, dict)]


def _last(request, *, mfa: bool) -> float:
    times = [
        float(r.get("at") or 0) for r in _records(request) if not mfa or r.get("method") == "mfa"
    ]
    return max(times, default=0.0)


def needs(user) -> str:
    """Womit das Konto bestätigt: ``code`` (2FA eingerichtet) oder ``password``."""
    return "code" if has_mfa(user) else "password"


def is_fresh(request, user) -> bool:
    return _last(request, mfa=has_mfa(user)) >= time.time() - FRESH_SECONDS


def require(request) -> None:
    """Vor einer heiklen Aktion aufrufen: ohne frische Bestätigung ``StepUpRequired``."""
    if not getattr(settings, "MFA_STEP_UP", True):
        return
    django_request = getattr(request, "_request", request)
    user = request.user
    if not is_fresh(django_request, user):
        raise StepUpRequired(needs(user))


def check_second_factor(user, code: str) -> bool:
    """TOTP-Code oder Wiederherstellungscode des Kontos prüfen."""
    from allauth.mfa.models import Authenticator
    from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
    from allauth.mfa.totp.internal.auth import TOTP

    code = "".join(str(code or "").split())
    if not code:
        return False
    for auth in Authenticator.objects.filter(user=user):
        if auth.type == Authenticator.Type.TOTP and TOTP(auth).validate_code(code):
            return True
        if auth.type == Authenticator.Type.RECOVERY_CODES and RecoveryCodes(auth).validate_code(
            code
        ):
            return True
    return False


def record(request, user, method: str, **extra) -> None:
    """Bestätigung in der Sitzung vermerken (wie allauth bei der Anmeldung)."""
    from allauth.account.internal.flows.login import record_authentication

    record_authentication(request, user, method, **extra)


class StepUpView(APIView):
    """POST ``{"code": …}`` oder ``{"password": …}``: heikle Aktionen kurz freigeben.

    GET sagt, womit bestätigt wird und ob die letzte Bestätigung noch frisch ist."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({"step_up": needs(user), "fresh": is_fresh(request._request, user)})

    def post(self, request):
        user = request.user
        key = f"step-up:{user.pk}"
        if too_many(key, RATE[0], RATE[1]):
            raise Throttled(detail=gettext("Zu viele Versuche. Bitte später erneut."))
        if has_mfa(user):
            if not check_second_factor(user, str(request.data.get("code") or "")):
                raise PermissionDenied(gettext("Der Code stimmt nicht."))
            record(request._request, user, "mfa", type="totp")
        else:
            if not user.check_password(str(request.data.get("password") or "")):
                raise PermissionDenied(gettext("Das Passwort stimmt nicht."))
            record(request._request, user, "password")
        return Response({"fresh": True})
