"""Hintergrundjobs der API für andere Programme."""

from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from .models import REMIND_BEFORE, ApiAccess


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
