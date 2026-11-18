from celery import shared_task


@shared_task
def daily() -> int:
    """Angaben von Gästen nach der Frist anonymisieren."""
    from .services import purge_due

    return purge_due()
