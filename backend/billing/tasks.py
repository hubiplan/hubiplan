"""Hintergrund-Jobs der Beiträge."""

from celery import shared_task


@shared_task
def archive_invoices() -> int:
    """Festgeschriebene Rechnungen als PDF ablegen (alle 15 Minuten, je 200)."""
    from .archive import archive_missing

    return archive_missing()


# Java-Prüfung je Eingang bis EINVOICE_VALIDATOR_BACKGROUND_TIMEOUT; je Lauf höchstens 50
@shared_task(soft_time_limit=3 * 60 * 60, time_limit=3 * 60 * 60 + 60)
def check_incoming(org_id: int) -> int:
    """Eingehende E-Rechnungen eines Vereins technisch prüfen (Gesamtaudit 10.11., S05)."""
    from .incoming_check import check_org

    return check_org(org_id)


@shared_task(soft_time_limit=3 * 60 * 60, time_limit=3 * 60 * 60 + 60)
def check_incoming_all() -> int:
    """Liegengebliebene Prüfungen nachholen (jede Minute)."""
    from .incoming_check import check_all

    return check_all()


@shared_task
def purge_rejected_incoming() -> int:
    """Abgelehnte und nicht lesbare Eingangsrechnungen nach 90 Tagen löschen (täglich).

    Löscht auch alte Einträge des Rechnungspostfachs (#374)."""
    from .incoming_check import purge_rejected
    from .incoming_mail import purge_old

    count = purge_rejected()
    purge_old()
    return count


@shared_task(soft_time_limit=9 * 60, time_limit=10 * 60)
def fetch_incoming_mail() -> int:
    """E-Rechnungen aus dem Rechnungspostfach abholen (jede Minute, #374)."""
    from .incoming_mail import fetch

    return fetch()
