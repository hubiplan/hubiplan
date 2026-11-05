"""Hintergrund-Jobs des Terminkalenders."""

from celery import shared_task

from . import notify


@shared_task
def send_event_mails(event_id: int, kind: str) -> int:
    """Einladung, Änderung oder Absage an die Eingeladenen."""
    return notify.send(event_id, kind)


@shared_task
def send_event_reminders() -> int:
    """Stündlich: fällige Erinnerungen verschicken."""
    return notify.send_reminders()


# Ruft fremde Server ab: Laufzeit begrenzen (Gesamtaudit 05.11. GA-03)
@shared_task(soft_time_limit=2700, time_limit=2760)
def sync_external_calendars() -> int:
    """Stündlich: Termine der fremden Kalender (Vereinsplaner, iCal) abholen."""
    from core.tenancy import rls_bypass

    from .external import sync_all

    with rls_bypass():
        return sync_all()
