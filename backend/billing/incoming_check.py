"""Eingehende E-Rechnungen im Hintergrund prüfen (Gesamtaudit 10.11., S05).

Die KoSIT-Prüfung (Java) braucht bis zu einer Minute. Sie läuft deshalb nicht beim
Hochladen und nicht unter der Finanzsperre des Vereins, sondern in einem Celery-Job. Der
Eingang zeigt so lange „Wird geprüft“. Je Verein läuft höchstens eine Prüfung gleichzeitig:
Wer die Sperre hat, arbeitet alle wartenden Eingänge des Vereins nacheinander ab. Ein
minütlicher Job holt liegengebliebene Eingänge nach (verlorener Auftrag, Neustart).

Abgelehnte und nicht lesbare Eingänge ohne Buchung werden nach
``EINVOICE_REJECTED_RETENTION_DAYS`` Tagen gelöscht, außer eine Löschsperre des
Geschäftsjahres steht dagegen.
"""

from __future__ import annotations

import datetime
import logging
from contextlib import contextmanager

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext

from . import einvoice_validator
from .models import IncomingInvoice

log = logging.getLogger(__name__)

# Zweiter Schlüssel der Beratungssperre je Verein (300000 ist die Finanzsperre)
LOCK_KEY = 300001


def pending_report() -> dict:
    return {"status": "pending", "validator": einvoice_validator.VERSION, "messages": []}


def schedule(org_id: int) -> None:
    """Prüfung nach dem Commit anstoßen. Fehlt der Broker, holt der minütliche Job sie nach."""

    def start():
        from .tasks import check_incoming

        try:
            check_incoming.delay(org_id)
        except Exception:  # noqa: BLE001 - Eingang ist gespeichert, der Nachlauf prüft ihn
            log.warning("E-Rechnungsprüfung für Einheit %s nicht angestoßen", org_id)

    transaction.on_commit(start)


@contextmanager
def _org_lock(org_id: int):
    """Sitzungssperre ohne Warten: True, wenn diese Verbindung den Verein prüfen darf."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", [org_id, LOCK_KEY])
        locked = cursor.fetchone()[0]
    try:
        yield locked
    finally:
        if locked:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s, %s)", [org_id, LOCK_KEY])


def check_org(org_id: int, limit: int = 50) -> int:
    """Wartende Eingänge eines Vereins prüfen; 0, wenn dort schon eine Prüfung läuft."""
    from core.tenancy import tenant_context

    done = 0
    with tenant_context(org_id), _org_lock(org_id) as locked:
        if not locked:
            return 0
        while done < limit:
            pk = (
                IncomingInvoice.objects.filter(organization_id=org_id, validation="pending")
                .order_by("pk")
                .values_list("pk", flat=True)
                .first()
            )
            if pk is None:
                break
            check_one(pk)
            done += 1
    return done


def check_one(pk: int) -> None:
    item = IncomingInvoice.objects.get(pk=pk)
    report, report_xml = einvoice_validator.failed(
        gettext("Keine unterstützte E-Rechnung erkannt.")
    )
    if item.xml:
        try:
            with item.xml.open("rb") as stream:
                xml = stream.read()
        except OSError:
            log.exception("E-Rechnung %s nicht lesbar", pk)
            report, report_xml = einvoice_validator.failed(
                gettext("Die E-Rechnungsprüfung konnte nicht abgeschlossen werden."),
                "unavailable",
            )
        else:
            # Ohne offene Transaktion und ohne Sperre: Java darf hier lange brauchen.
            report, report_xml = einvoice_validator.validate(
                xml, timeout=settings.EINVOICE_VALIDATOR_BACKGROUND_TIMEOUT
            )
    with transaction.atomic():
        locked = IncomingInvoice.objects.select_for_update().get(pk=pk)
        if locked.validation != "pending" or locked.xml.name != item.xml.name:
            return
        locked.report, locked.validation = report, "done"
        if report_xml:
            locked.report_xml.save("validation.xml", ContentFile(report_xml), save=False)
        locked.save()


def check_all() -> int:
    """Alle Vereine mit wartenden Eingängen prüfen (minütlicher Nachlauf)."""
    from core.tenancy import rls_bypass

    with rls_bypass():
        orgs = sorted(
            set(
                IncomingInvoice.objects.filter(validation="pending").values_list(
                    "organization_id", flat=True
                )
            )
        )
    return sum(check_org(org_id) for org_id in orgs)


def _deletable(item: IncomingInvoice, cutoff: datetime.datetime) -> bool:
    if item.booking_id or item.status == "approved":
        return False
    if item.status == "rejected":
        return item.reviewed_at is not None and item.reviewed_at < cutoff
    # Nicht lesbar: keine Rechnungsdaten, also keine E-Rechnung. Lesbare, aber fehlerhafte
    # Rechnungen bleiben, bis jemand sie ablehnt.
    return item.validation == "done" and not item.data and item.created_at < cutoff


def _held(item: IncomingInvoice) -> bool:
    from finance.models import YearClosing

    year = item.organization.fiscal_year_of(timezone.localdate(item.created_at))
    return (
        YearClosing.objects.filter(organization_id=item.organization_id, year=year)
        .exclude(retention_hold="")
        .exists()
    )


def purge_rejected(now: datetime.datetime | None = None) -> int:
    """Abgelehnte und nicht lesbare Eingänge ohne Buchung nach Ablauf der Frist löschen."""
    from audit.log import record
    from core.files import delete_on_commit
    from core.tenancy import rls_bypass, tenant_context

    days = settings.EINVOICE_REJECTED_RETENTION_DAYS
    cutoff = (now or timezone.now()) - datetime.timedelta(days=days)
    with rls_bypass():
        rows = list(
            IncomingInvoice.objects.filter(booking__isnull=True)
            .filter(
                Q(status="rejected", reviewed_at__lt=cutoff)
                | Q(status="review", validation="done", created_at__lt=cutoff)
            )
            .order_by("pk")
            .values_list("pk", "organization_id")
        )
    count = 0
    for pk, org_id in rows:
        with tenant_context(org_id), transaction.atomic():
            item = (
                IncomingInvoice.objects.select_for_update()
                .select_related("organization")
                .filter(pk=pk)
                .first()
            )
            if item is None or not _deletable(item, cutoff) or _held(item):
                continue
            for check in item.previous_checks.all():
                delete_on_commit(check.report_xml)
                check.delete()
            delete_on_commit(item.original, item.xml, item.report_xml)
            reason = "abgelehnt" if item.status == "rejected" else "nicht lesbar"
            record(
                item.organization,
                None,
                "delete",
                item,
                {"Rechnungseingang": [reason, f"nach {days} Tagen gelöscht"]},
            )
            item.delete()
            count += 1
    return count
