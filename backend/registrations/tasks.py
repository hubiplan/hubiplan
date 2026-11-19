from celery import shared_task


@shared_task
def daily() -> int:
    """Unbezahlte Anmeldungen verfallen lassen, beendete Wartelisten schließen und Angaben von
    Gästen nach der Frist anonymisieren; Gesundheitsangaben 14 Tage nach dem Ende löschen;
    unbestätigte Anmeldungen aus dem öffentlichen Formular nach 24 Stunden löschen."""
    from .extras import purge_health_due
    from .public import purge_pending
    from .services import close_waitlists, expire_due, purge_due

    return expire_due() + close_waitlists() + purge_due() + purge_health_due() + purge_pending()
