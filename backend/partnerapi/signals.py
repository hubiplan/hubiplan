"""Änderungen an Mitgliedern und Terminen für die Benachrichtigungen der API bemerken.

Beim Speichern selbst passiert nichts außer dem Vormerken: Geprüft und eingereiht wird erst
nach dem Abschluss der Änderung (``transaction.on_commit``). So kostet die API das normale
Arbeiten keine Datenbankabfrage, und eine verworfene Änderung meldet nichts.
"""

from __future__ import annotations

import logging
from functools import partial

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from changes import tracking
from core.tenancy import rls_bypass

from . import refs, webhooks

logger = logging.getLogger(__name__)


def _later(func, *args) -> None:
    if settings.PARTNER_API_ENABLED:
        transaction.on_commit(partial(_safely, func, *args))


def _safely(func, *args) -> None:
    try:
        func(*args)
    except Exception:  # noqa: BLE001 (eine Benachrichtigung darf keine Änderung stören)
        logger.exception("API-Benachrichtigung: Änderung konnte nicht vorgemerkt werden")


def _member(org_id: int, membership_id: int, event: str, touch: bool = False) -> None:
    from members.models import Membership

    if touch:
        # Eintritt, Austritt, Mitgliedsart und Untereinheit zählen für ``changed_since`` mit
        with rls_bypass(), tracking.suppress():
            Membership.objects.filter(pk=membership_id).update(updated_at=timezone.now())
    webhooks.emit(org_id, event, refs.MEMBER, membership_id)


def _person(person_id: int) -> None:
    from members.models import Membership

    if not webhooks.any_hooks():
        return
    with rls_bypass():
        rows = list(
            Membership.objects.filter(person_id=person_id, purged_at__isnull=True).values_list(
                "organization_id", "pk"
            )
        )
    for org_id, membership_id in rows:
        webhooks.emit(org_id, webhooks.MEMBER_CHANGED, refs.MEMBER, membership_id)


def _event(org_id, event_id, code, visibility, department_id) -> None:
    webhooks.emit(
        org_id, code, "event", event_id, visibility=visibility, department_id=department_id
    )


def connect() -> None:
    from events.models import Event
    from members.models import (
        ContactDetails,
        DepartmentMembership,
        Membership,
        MembershipPeriod,
        MemberTypeAssignment,
        Person,
    )

    @receiver(post_save, sender=Membership, weak=False, dispatch_uid="partnerapi_membership")
    def membership_saved(sender, instance, created, **kwargs):
        if created:
            code = webhooks.MEMBER_CREATED
        elif instance.purged_at:
            code = webhooks.MEMBER_DELETED
        else:
            code = webhooks.MEMBER_CHANGED
        _later(_member, instance.organization_id, instance.pk, code)

    @receiver(post_delete, sender=Membership, weak=False, dispatch_uid="partnerapi_membership_del")
    def membership_deleted(sender, instance, **kwargs):
        _later(_member, instance.organization_id, instance.pk, webhooks.MEMBER_DELETED)

    @receiver(post_save, sender=MembershipPeriod, weak=False, dispatch_uid="partnerapi_period")
    def period_saved(sender, instance, **kwargs):
        code = webhooks.MEMBER_LEFT if instance.exit_date else webhooks.MEMBER_CHANGED
        _later(_member, instance.organization_id, instance.membership_id, code, True)

    for model in (MemberTypeAssignment, DepartmentMembership):

        @receiver(post_save, sender=model, weak=False, dispatch_uid=f"partnerapi_{model.__name__}")
        def part_saved(sender, instance, **kwargs):
            _later(
                _member,
                instance.organization_id,
                instance.membership_id,
                webhooks.MEMBER_CHANGED,
                True,
            )

    @receiver(post_save, sender=Person, weak=False, dispatch_uid="partnerapi_person")
    def person_saved(sender, instance, created, **kwargs):
        if not created:
            _later(_person, instance.pk)

    @receiver(post_save, sender=ContactDetails, weak=False, dispatch_uid="partnerapi_contact")
    def contact_saved(sender, instance, **kwargs):
        _later(_person, instance.person_id)

    def own_event(instance) -> bool:
        return not instance.remote_uid and instance.external_source_id is None

    @receiver(post_save, sender=Event, weak=False, dispatch_uid="partnerapi_event")
    def event_saved(sender, instance, created, **kwargs):
        if not own_event(instance):
            return
        if created:
            code = webhooks.EVENT_CREATED
        elif instance.is_cancelled:
            code = webhooks.EVENT_CANCELLED
        else:
            code = webhooks.EVENT_CHANGED
        _later(
            _event,
            instance.organization_id,
            instance.pk,
            code,
            instance.visibility,
            instance.department_id,
        )

    @receiver(post_delete, sender=Event, weak=False, dispatch_uid="partnerapi_event_del")
    def event_deleted(sender, instance, **kwargs):
        if own_event(instance):
            _later(
                _event,
                instance.organization_id,
                instance.pk,
                webhooks.EVENT_DELETED,
                instance.visibility,
                instance.department_id,
            )
