from celery import shared_task


@shared_task
def send_reminders() -> int:
    from .notify import send_reminders as run

    return run()
