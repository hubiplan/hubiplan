from celery import shared_task


@shared_task
def daily() -> int:
    """Unbezahlte Anmeldungen verfallen lassen, beendete Wartelisten schließen und Angaben von
    Gästen nach der Frist anonymisieren."""
    from .services import close_waitlists, expire_due, purge_due

    return expire_due() + close_waitlists() + purge_due()
