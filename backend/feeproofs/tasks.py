from celery import shared_task


@shared_task
def send_notices() -> int:
    from .notify import run

    return run()


@shared_task
def cleanup() -> dict:
    from .notify import cleanup as run

    return run()
