"""Geräte abmelden, wenn sich das Passwort ändert oder der Zugang endet."""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.utils import timezone


def revoke_devices(user) -> int:
    from .models import Device

    if user is None or user.pk is None:
        return 0
    return Device.objects.filter(user=user, revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )


def _on_password_change(sender, request=None, user=None, **kwargs):
    revoke_devices(user)


def _nothing_left(user) -> bool:
    """Weder Zugang zum Mitgliederbereich noch etwas zu verwalten: Die App zeigt nichts mehr."""
    from core.tenancy import user_view
    from portal.models import PortalAccess

    from .access import manages_in_app

    if user is None or user.pk is None:
        return False
    # Zugänge in allen Vereinen zählen, nicht nur die im Verein des Löschenden: In dessen
    # Sicht fehlen die übrigen Zugänge unter RLS (Gesamtaudit 31.10.b, AT-F01)
    with user_view(user.pk):
        if PortalAccess.objects.filter(user_id=user.pk).exists():
            return False
    return not manages_in_app(user)


def _on_access_deleted(sender, instance, **kwargs):
    # Konten mit Rolle behalten die App für die Verwaltung
    if _nothing_left(instance.user):
        revoke_devices(instance.user)


def _on_role_changed(sender, instance, **kwargs):
    # Rolle entzogen oder beendet: ohne Mitgliederbereich und ohne weitere Rolle Geräte abmelden.
    # Nur wenn es überhaupt ein Gerät gibt, damit die Rollenverwaltung nicht langsamer wird
    from django.db import transaction

    from accounts.models import User

    from .models import Device

    # Wird das Konto selbst gelöscht, fallen seine Rollen mit weg: Dann ist nichts abzumelden
    user = User.objects.filter(pk=instance.user_id).first() if instance.user_id else None
    if user is None or not Device.objects.filter(user=user, revoked_at__isnull=True).exists():
        return

    def check():
        if _nothing_left(user):
            revoke_devices(user)

    transaction.on_commit(check)


def connect() -> None:
    from allauth.account import signals as account_signals

    from portal.models import PortalAccess

    for signal in (account_signals.password_changed, account_signals.password_reset):
        signal.connect(_on_password_change, dispatch_uid=f"devices-{id(signal)}")
    post_delete.connect(_on_access_deleted, sender=PortalAccess, dispatch_uid="devices-access")
    from access.models import RoleAssignment

    post_delete.connect(_on_role_changed, sender=RoleAssignment, dispatch_uid="devices-role-del")
    post_save.connect(_on_role_changed, sender=RoleAssignment, dispatch_uid="devices-role-save")
