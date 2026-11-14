from celery import shared_task


@shared_task
def notify_start(survey_id: int) -> int:
    from .notify import START, send

    return send(survey_id, START)


@shared_task
def hourly() -> dict:
    """Abgelaufene Umfragen schließen, erinnern, nach der Frist aufräumen."""
    from . import notify, services

    return {
        "closed": services.close_due(),
        "reminded": notify.send_reminders(),
        "purged": services.purge_due(),
    }
