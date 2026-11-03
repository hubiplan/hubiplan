"""Offene Anmelde- und Bestätigungslinks bei Sicherheitsänderungen am Konto widerrufen.

Ändert jemand Passwort, Anmelde-E-Mail oder richtet 2FA ein, gelten vorher
verschickte Links (Anmeldelink, E-Mail-Bestätigung) und offene QR-Codes zum
Verbinden der App nicht mehr. Neue Links und Codes lassen sich danach normal
anfordern. Ein Passwortwechsel oder -reset meldet zusätzlich alle App-Geräte ab
(``devices.signals``; der eigene Endpunkt in ``self_service.PasswordView`` ruft
``secure_account`` direkt auf, weil er keine allauth-Signale sendet).
"""

from __future__ import annotations

from django.contrib.auth import update_session_auth_hash
from django.db import transaction
from django.utils import timezone

from core.tenancy import rls_bypass


def revoke_links(user) -> None:
    from accounts.models import EmailChange
    from devices.models import PairingCode
    from portal.models import LoginLink

    if user is None or user.pk is None:
        return
    now = timezone.now()
    with rls_bypass():
        LoginLink.objects.filter(user=user, used_at__isnull=True).update(used_at=now)
        EmailChange.objects.filter(user=user, used_at__isnull=True).delete()
        PairingCode.objects.filter(user=user, used_at__isnull=True).update(used_at=now)


def secure_account(user, *, devices: bool, request=None, recovery: bool = False) -> None:
    """Zentrale Reaktion auf eine Sicherheitsänderung am Konto.

    Erhöht die Authentifizierungsversion und widerruft ältere Browser-/OIDC-Anmeldungen
    sowie offene Links und QR-Codes. Mit ``devices=True`` werden App-Geräte abgemeldet.
    Nur die ausdrücklich übergebene eigene Sitzung darf bestehen bleiben. Administrative
    Recovery entfernt zusätzlich eingehende Peer-Anmeldeverknüpfungen.
    """
    from accounts.models import User

    if user is None or user.pk is None:
        return
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        user.auth_version = locked.auth_version + 1
        User.objects.filter(pk=user.pk).update(auth_version=user.auth_version)
        revoke_links(user)
        if recovery:
            from peering.models import LoginLink

            LoginLink.objects.filter(user=user).delete()
    if devices:
        from devices.signals import revoke_devices

        revoke_devices(user)
    if request is not None and request.user == user:
        update_session_auth_hash(request, user)


def _on_security_change(sender, request=None, user=None, **kwargs):
    secure_account(user, devices=False, request=request)


def _on_mfa_removed(sender, request=None, user=None, **kwargs):
    # Die Sitzung darf für die Neueinrichtung bestehen bleiben. Ein historischer
    # MFA-Eintrag ist nach Entfernen/Zurücksetzen aber kein gültiger zweiter Faktor.
    from allauth.account.internal.flows.login import AUTHENTICATION_METHODS_SESSION_KEY

    if request is not None and request.user == user:
        request.session[AUTHENTICATION_METHODS_SESSION_KEY] = [
            record
            for record in request.session.get(AUTHENTICATION_METHODS_SESSION_KEY, [])
            if isinstance(record, dict) and record.get("method") != "mfa"
        ]
        request.session.pop("peering_sso_stepup", None)
    secure_account(user, devices=False, request=request)


def connect() -> None:
    from allauth.account import signals as account_signals
    from allauth.mfa import signals as mfa_signals

    for signal in (
        account_signals.password_changed,
        account_signals.password_set,
        account_signals.password_reset,
        mfa_signals.authenticator_added,
    ):
        signal.connect(_on_security_change, dispatch_uid=f"revoke-links-{id(signal)}")
    for signal in (mfa_signals.authenticator_removed, mfa_signals.authenticator_reset):
        signal.connect(_on_mfa_removed, dispatch_uid=f"revoke-links-{id(signal)}")
