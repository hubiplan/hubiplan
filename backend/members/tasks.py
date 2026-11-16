"""Hintergrund-Jobs der Mitgliederverwaltung."""

import logging

from celery import shared_task

from .workflows import purge_expired, purge_lock

logger = logging.getLogger(__name__)


@shared_task
def purge_expired_members() -> int | None:
    """Täglich: Daten ehemaliger Mitglieder nach Ablauf der Löschfrist löschen.

    Läuft schon ein Löschlauf (Nachholen nach Neustart, Befehl von Hand), endet dieser
    sofort mit None (Gesamtaudit 15.11., PF-10)."""
    from . import loeschliste

    with purge_lock() as locked:
        if not locked:
            logger.warning("Löschfrist: ein anderer Löschlauf läuft noch, übersprungen")
            return None
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
