"""Hintergrund-Jobs der Online-Anträge."""

from celery import shared_task

from .services import purge


@shared_task
def purge_applications() -> int:
    """Stündlich: unbestätigte Anträge nach 48 Stunden, abgelehnte nach der Frist löschen."""
    return purge()
