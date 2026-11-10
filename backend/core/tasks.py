"""Hintergrund-Jobs. Bisher nur ein Test-Job, um die Celery-Anbindung zu prüfen."""

from celery import shared_task

# Jobs in eigenen Modulen; der Import meldet sie beim Worker an (Celery sucht nur tasks.py)
from .backup_status import check_backup  # noqa: F401
from .update_check import check_latest  # noqa: F401


@shared_task
def ping() -> str:
    return "pong"


@shared_task
def recheck_quarantine() -> dict:
    """Dateien in Quarantäne nachprüfen, sobald der Virenscanner wieder antwortet."""
    from .virenscan import recheck_quarantine as recheck

    return recheck()


def enqueue(task, job, *, failed_status: str, message: str = "") -> bool:
    """Hintergrund-Job an Celery übergeben. Ist der Dienst nicht erreichbar, bleibt der
    Auftrag nicht unbemerkt „läuft“ stehen: Status zurück und Hinweis zum Neustart."""
    import logging

    try:
        task.delay(job.pk)
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).exception("Job %s konnte nicht gestartet werden", job.pk)
        job.status = failed_status
        job.error = message or (
            "Der Hintergrunddienst war nicht erreichbar, es wurde nichts verändert. "
            "Bitte noch einmal starten."
        )
        job.save(update_fields=["status", "error"])
        return False
    return True
