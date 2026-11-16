from celery import shared_task


@shared_task
def daily():
    """Aufbewahrung: Belege abgelehnter Anträge, alte Entwürfe (AE-11)."""
    from . import services

    return services.purge()
