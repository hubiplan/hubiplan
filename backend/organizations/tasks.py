"""Hintergrund-Jobs der Einheiten."""

from celery import shared_task


# Ruft fremde Server ab: Laufzeit begrenzen (Gesamtaudit 05.11. GA-03)
@shared_task(soft_time_limit=120, time_limit=180)
def fetch_homepage_preview(unit_id: int) -> bool:
    """Vorschaubild der Homepage einer Untereinheit holen (einmal je Adresse)."""
    from core.tenancy import rls_bypass

    from .homepage_preview import needs_refresh, refresh
    from .models import Department

    with rls_bypass():
        unit = Department.objects.filter(pk=unit_id).first()
        if unit is None or not needs_refresh(unit):
            return False
        return refresh(unit) == ""
