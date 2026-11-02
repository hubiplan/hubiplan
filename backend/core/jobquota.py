"""Obergrenzen für aufwendige Hintergrund-Jobs je Organisation (Gesamtaudit 30.10., B-V03).

Exporte und Importe sind teuer (Arbeitsspeicher, Dateien, Warteschlange). Ein einzelnes
(auch übernommenes) Konto soll die Instanz damit nicht auslasten können.
"""

from __future__ import annotations

import datetime
import zlib

from django.db import connection
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework.exceptions import Throttled

# Eigener Schlüsselbereich für pg_advisory_xact_lock (andere Sperren nutzen Jahreszahlen)
LOCK_BASE = 400_000_000


def _lock(qs, org_id: int) -> None:
    """Sperre je Organisation und Job-Art bis zum Ende der Transaktion (Audit 02.11., BP-S02).

    Zwei gleichzeitige Anfragen zählen sonst beide denselben freien Platz und legen
    beide einen Job an. Mit der Sperre zählt die zweite erst, wenn die erste ihren Job
    angelegt (oder aufgegeben) hat.
    """
    if not connection.in_atomic_block:
        raise RuntimeError("ensure_capacity nur innerhalb einer Transaktion aufrufen.")
    kind = LOCK_BASE + zlib.crc32(qs.model._meta.label.encode()) % 1_000_000
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", [org_id, kind])


def ensure_capacity(
    qs, *, org_id: int, active_statuses, max_active: int, max_per_hour: int, what: str
):
    """Fehler 429, wenn zu viele Jobs laufen oder in der letzten Stunde begonnen wurden.

    ``qs``: Jobs dieser Organisation (und Art). Muss in derselben Transaktion aufgerufen
    werden, die danach den Job anlegt; bis zu deren Ende wartet jede weitere Prüfung.
    """
    _lock(qs, org_id)
    if qs.filter(status__in=active_statuses).count() >= max_active:
        raise Throttled(
            detail=gettext(
                "Es laufen schon {max_active} {what}. Bitte warten, bis einer fertig ist."
            ).format(max_active=max_active, what=what)
        )
    since = timezone.now() - datetime.timedelta(hours=1)
    if qs.filter(created_at__gte=since).count() >= max_per_hour:
        raise Throttled(
            detail=gettext(
                "In der letzten Stunde wurden schon {max_per_hour} {what} begonnen. "
                "Bitte später erneut versuchen."
            ).format(max_per_hour=max_per_hour, what=what)
        )
