"""Hintergrund-Jobs der Mitgliederverwaltung."""

import logging

from celery import shared_task

from .workflows import purge_expired

logger = logging.getLogger(__name__)


@shared_task
def purge_expired_members() -> int:
    """Täglich: Daten ehemaliger Mitglieder nach Ablauf der Löschfrist löschen."""
    from . import loeschliste

    # Löschliste zuerst (falls ein älteres Backup eingespielt wurde, Fachfrage 7)
    loeschliste.apply()
    count = purge_expired()
    logger.info("Löschfrist: %s Mitgliedschaften bereinigt", count)
    return count


@shared_task
def end_guardianships() -> int:
    """Täglich: Erziehungsberechtigte vier Wochen vor dem 18. Geburtstag benachrichtigen und
    am Geburtstag samt Elternzugang beenden (Konzept Familien, H4)."""
    from . import guardians

    sent = guardians.send_notices()
    ended = guardians.end_adults()
    logger.info("Erziehungsberechtigte: %s Hinweise, %s beendet", sent, ended)
    return ended
