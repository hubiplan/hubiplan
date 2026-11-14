"""Verwaltung in der App über den Browser freischalten (iOS, Passkey; docs/app.md).

iOS gibt Passkeys einer App nur für fest eingetragene Adressen heraus. Die iOS-App schaltet
die Verwaltung deshalb über den eingebetteten Browser frei:

1. App (Geräteschlüssel): ``POST admin/unlock/browser/`` mit ``admin_key`` → ``ticket``
   (10 Minuten, an Gerät, Konto und Vorstands-Schlüsselpaar gebunden).
2. Browser ``/app/freischalten#t=<ticket>``: Anmelden (auf Wunsch mit Passkey), dann
   ``POST admin/unlock/browser/confirm/`` mit ``{"ticket", "confirm": true}``. Verlangt eine
   eingerichtete Zwei-Faktor-Anmeldung und eine frische Bestätigung (``accounts/step_up.py``).
   Antwort ``redirect``: ``hubiplan://freischalten?ticket=<ticket>``.
3. App: ``POST admin/unlock/`` mit ``browser_ticket`` und demselben ``admin_key``.
"""

from __future__ import annotations

import hashlib
import secrets
import time

from django.core.cache import cache
from django.utils.translation import gettext
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import step_up
from accounts.mfa_policy import has_mfa
from core.ratelimit import TooMany, too_many

from .models import Device

TICKET_SECONDS = 10 * 60


def _key(ticket: str) -> str:
    return "app:admin-browser:" + hashlib.sha256(str(ticket).encode()).hexdigest()


def _expired():
    return NotFound(
        gettext("Die Freischaltung ist abgelaufen. Bitte in der App noch einmal beginnen.")
    )


def start(device: Device, user, admin_key: str) -> str:
    ticket = secrets.token_urlsafe(32)
    cache.set(
        _key(ticket),
        {
            "device": device.pk,
            "user": user.pk,
            "admin_key": admin_key,
            "confirmed": False,
            "until": time.time() + TICKET_SECONDS,
        },
        TICKET_SECONDS,
    )
    return ticket


def _entry(ticket: str) -> dict | None:
    entry = cache.get(_key(ticket))
    if not isinstance(entry, dict) or entry.get("until", 0) < time.time():
        return None
    return entry


def redeem(ticket: str, device: Device, admin_key: str) -> bool:
    """Bestätigtes Ticket dieses Geräts einlösen (einmal nutzbar)."""
    key = _key(ticket)
    entry = _entry(ticket)
    if (
        entry is None
        or not entry.get("confirmed")
        or entry.get("device") != device.pk
        or entry.get("user") != device.user_id
        or entry.get("admin_key") != admin_key
    ):
        return False
    return bool(cache.delete(key))


class BrowserUnlockConfirmView(APIView):
    """Im Browser: Freischaltung der Verwaltung für ein Gerät bestätigen.

    ``{"ticket"}`` nennt nur das Gerät; mit ``"confirm": true`` wird bestätigt."""

    # Nur mit Browser-Sitzung, nie mit einem Geräteschlüssel
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        limit = f"app-admin-browser:{user.pk}"
        if too_many(limit, 20, 15 * 60):
            raise TooMany(limit)
        ticket = str(request.data.get("ticket") or "")[:100]
        entry = _entry(ticket) if ticket else None
        if entry is None or entry.get("user") != user.pk:
            raise _expired()
        device = Device.objects.filter(pk=entry.get("device"), user=user).first()
        if device is None or not device.is_active:
            raise _expired()
        if not has_mfa(user):
            raise ValidationError(
                {
                    "detail": gettext(
                        "Für die Verwaltung in der App ist die Zwei-Faktor-Anmeldung nötig. "
                        "Bitte zuerst im Browser unter „Mein Konto“ einrichten."
                    )
                }
            )
        if request.data.get("confirm") is not True:
            return Response({"device": device.name, "confirmed": False})
        # Frischer zweiter Faktor: Anmeldung mit Passkey zählt, sonst Passkey oder Code
        step_up.require(request)
        entry["confirmed"] = True
        remaining = max(1, int(entry["until"] - time.time()))
        cache.set(_key(ticket), entry, remaining)
        return Response(
            {
                "device": device.name,
                "confirmed": True,
                "redirect": f"hubiplan://freischalten?ticket={ticket}",
            }
        )
