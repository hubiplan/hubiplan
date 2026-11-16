"""Hintergrund-Jobs der Rundschreiben."""

from celery import shared_task

from core.einzeln import LONG_HARD, LONG_SOFT

from . import services


@shared_task(soft_time_limit=LONG_SOFT, time_limit=LONG_HARD)
def send_circular(circular_id: int) -> int:
    """Offene Mails eines Rundschreibens verschicken."""
    return services.send_pending(circular_id)


# Ruft fremde Server ab: Laufzeit begrenzen (Gesamtaudit 05.11. GA-03)
@shared_task(soft_time_limit=1500, time_limit=1560)
def fetch_inbound() -> int:
    """Mailverteiler: Sammelpostfach abholen."""
    from . import inbound

    return inbound.fetch_inbound()


@shared_task
def resume_stalled() -> int:
    """Hängengebliebene Rundschreiben weiterversenden (alle 15 Minuten)."""
    return services.resume_stalled()
