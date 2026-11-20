from celery import shared_task


@shared_task
def notify(notice_id: int) -> int:
    from .notify import send

    return send(notice_id)


@shared_task
def daily() -> int:
    """Abgelaufene Beiträge aufräumen."""
    from .services import purge_due

    return purge_due()
