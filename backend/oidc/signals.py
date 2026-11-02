"""Ändern sich Rollen, Ämter, Mitgliederzugang oder Konto, die Nextcloud-Konten abgleichen.

Nur wenn der Benutzer ein über HUBIplan angemeldetes Konto bei einem Dienst mit „Konten
automatisch deaktivieren“ hat; sonst passiert nichts. Der Abgleich läuft nach dem Speichern
als Hintergrundauftrag.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from access.models import RoleAssignment
from accounts.models import User
from core.tenancy import rls_bypass
from members.models import DepartmentRoleHolder, MembershipPeriod
from portal.models import PortalAccess

from .models import Account


def _queue(user_ids: set[int]) -> None:
    user_ids.discard(None)
    if not user_ids:
        return
    with rls_bypass():
        known = set(
            Account.objects.filter(user_id__in=user_ids, client__manage_accounts=True).values_list(
                "user_id", flat=True
            )
        )
    for user_id in known:
        from .tasks import sync_user

        transaction.on_commit(lambda uid=user_id: sync_user.delay(uid))


def _users_of_membership(membership_id) -> set[int]:
    if not membership_id:
        return set()
    with rls_bypass():
        return set(
            PortalAccess.objects.filter(membership_id=membership_id).values_list(
                "user_id", flat=True
            )
        )


@receiver([post_save, post_delete], sender=RoleAssignment)
@receiver([post_save, post_delete], sender=DepartmentRoleHolder)
def _role_changed(sender, instance, **kwargs):
    users = {instance.user_id} | _users_of_membership(instance.membership_id)
    _queue(users)


@receiver([post_save, post_delete], sender=PortalAccess)
def _access_changed(sender, instance, **kwargs):
    _queue({instance.user_id})


@receiver([post_save, post_delete], sender=MembershipPeriod)
def _period_changed(sender, instance, **kwargs):
    _queue(_users_of_membership(instance.membership_id))


@receiver(post_save, sender=User)
def _user_changed(sender, instance, update_fields=None, **kwargs):
    if update_fields is not None and "is_active" not in update_fields:
        return
    _queue({instance.pk})
