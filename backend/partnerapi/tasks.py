"""Hintergrundjobs der API für andere Programme."""

from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from .models import (
    IDEMPOTENCY_KEEP,
    LOG_KEEP,
    REMIND_BEFORE,
    ApiAccess,
    IdempotencyKey,
    ReadLog,
    WebhookDelivery,
)


@shared_task
def remind_expiring() -> int:
    """30 Tage vor dem Ablauf einmal an alle erinnern, die API-Zugänge verwalten dürfen."""
    from changes import tracking
    from core.tenancy import rls_bypass

    from . import notify
    from .auth import enabled_for

    now = timezone.now()
    count = 0
    with rls_bypass():
        due = list(
            ApiAccess.objects.select_related("organization", "unit").filter(
                expires_at__gt=now, expires_at__lte=now + REMIND_BEFORE, reminded_at__isnull=True
            )
        )
    for access in due:
        # Ruhende Zugänge und abgeschaltete Module: keine Erinnerung, es fließt ohnehin nichts
        if not access.is_active or not enabled_for(access.organization):
            continue
        with tracking.suppress(), rls_bypass():
            updated = ApiAccess.objects.filter(pk=access.pk, reminded_at__isnull=True).update(
                reminded_at=now
            )
        if updated:
            notify.expiring(access)
            count += 1
    return count


@shared_task
def deliver_webhooks() -> int:
    """Fällige Benachrichtigungen an die Adressen der Zugänge zustellen (jede Minute)."""
    from . import webhooks

    return webhooks.deliver_due()


@shared_task
def purge_logs() -> int:
    """Abrufprotokoll und erledigte Benachrichtigungen nach 90 Tagen löschen, den
    Wiederholungsschutz des Schreibens nach 24 Stunden."""
    from django.db.models import Q

    from changes import tracking
    from core.tenancy import rls_bypass

    before = timezone.now() - LOG_KEEP
    with tracking.suppress(), rls_bypass():
        logs, _ = ReadLog.objects.filter(at__lt=before).delete()
        hooks, _ = (
            WebhookDelivery.objects.filter(occurred_at__lt=before)
            .filter(Q(delivered_at__isnull=False) | Q(dropped_at__isnull=False))
            .delete()
        )
        keys, _ = IdempotencyKey.objects.filter(
            created_at__lt=timezone.now() - IDEMPOTENCY_KEEP
        ).delete()
    return logs + hooks + keys
