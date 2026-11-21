from celery import shared_task


@shared_task
def daily() -> int:
    """Anwesenheit und Schießbuch nach zehn Jahren löschen."""
    from .services import purge_due

    return purge_due()
