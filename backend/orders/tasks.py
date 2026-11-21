from celery import shared_task


@shared_task
def notify(campaign_id: int) -> int:
    from .notify import send

    return send(campaign_id)


@shared_task
def daily() -> int:
    """Alte Sammelbestellungen aufräumen."""
    from .services import purge_due

    return purge_due()
