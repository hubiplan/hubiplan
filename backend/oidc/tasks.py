from celery import shared_task

from core.einzeln import einzeln

from . import nc_accounts


# Ruft fremde Server ab: Laufzeit begrenzen (Gesamtaudit 05.11. GA-03)
@shared_task(soft_time_limit=300, time_limit=360)
def sync_user(user_id: int) -> None:
    """Rollen oder Konto eines Benutzers haben sich geändert: Nextcloud-Konten abgleichen."""
    nc_accounts.sync_user(user_id)


@shared_task(soft_time_limit=120, time_limit=180)
def disable_deleted(client_id: int, nc_user: str) -> bool:
    """Nach dem Löschen eines HUBIplan-Kontos dessen Nextcloud-Konto deaktivieren."""
    return nc_accounts.disable_deleted(client_id, nc_user)


@shared_task
def sync_all() -> None:
    """Nächtlicher Abgleich (auch Rollen, die zu einem Datum enden)."""
    nc_accounts.sync_all()


# Schreibt in fremde Server: Laufzeit begrenzen, nie zwei Läufe gleichzeitig
@shared_task(soft_time_limit=1500, time_limit=1560)
@einzeln
def sync_calendars() -> int:
    """Alle 15 Minuten: Termine in die Kalender der Nextcloud schreiben."""
    from . import nc_calendars

    return nc_calendars.sync_all()


@shared_task(soft_time_limit=600, time_limit=660)
def sync_client_calendars(client_id: int, unshare: dict | None = None) -> dict:
    """Nach dem Speichern der Einstellungen oder auf Knopfdruck: einen Dienst abgleichen."""
    from . import nc_calendars

    return nc_calendars.sync_client(client_id, unshare)
