"""Regelmäßige Aufgaben des Mitgliederbereichs."""

from __future__ import annotations

import datetime

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from core.tenancy import rls_bypass

# Benutzte oder abgelaufene Anmeldelinks bleiben so lange zur Nachverfolgung stehen
KEEP_DAYS = 30


@shared_task
def purge_login_links() -> int:
    """Alte Anmeldelinks löschen (Gesamtaudit 11.11., H-07).

    Offene Links bleiben; benutzte und abgelaufene verschwinden nach 30 Tagen.
    """
    from .models import LoginLink

    cutoff = timezone.now() - datetime.timedelta(days=KEEP_DAYS)
    with rls_bypass():
        deleted, _ = LoginLink.objects.filter(
            Q(used_at__lt=cutoff) | Q(expires_at__lt=cutoff)
        ).delete()
    return deleted
