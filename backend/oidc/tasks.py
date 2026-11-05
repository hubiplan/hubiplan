from celery import shared_task

from . import nc_accounts


# Ruft fremde Server ab: Laufzeit begrenzen (Gesamtaudit 05.11. GA-03)
@shared_task(soft_time_limit=300, time_limit=360)
def sync_user(user_id: int) -> None:
    """Rollen oder Konto eines Benutzers haben sich geändert: Nextcloud-Konten abgleichen."""
    nc_accounts.sync_user(user_id)


@shared_task
def sync_all() -> None:
    """Nächtlicher Abgleich (auch Rollen, die zu einem Datum enden)."""
    nc_accounts.sync_all()
