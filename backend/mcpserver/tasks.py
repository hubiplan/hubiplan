"""Hintergrundjobs der KI-Schnittstelle."""

from __future__ import annotations

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from .models import IDLE_LIFETIME, McpGrant


@shared_task
def purge_retired_refresh() -> int:
    """Frühere Erneuerungsschlüssel beendeter Verbindungen vergessen (Gesamtaudit 15.11.,
    MCP-04). Laufende Verbindungen gelten höchstens 30 Tage; ihre Liste bleibt, damit jede
    Kopie auffällt."""
    from core.tenancy import rls_bypass

    now = timezone.now()
    with rls_bypass():
        return (
            McpGrant.objects.exclude(retired_refresh_hashes=[])
            .filter(
                Q(revoked_at__isnull=False)
                | Q(expires_at__lte=now)
                | Q(last_used_at__lte=now - IDLE_LIFETIME)
            )
            .update(retired_refresh_hashes=[])
        )
