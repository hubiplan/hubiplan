"""Langläufer nie doppelt: Sitzungssperre der Datenbank je Aufgabe (Gesamtaudit 15.11., PF-08/13).

Minutenjobs wie die E-Rechnungsprüfung oder der Postfachabruf können länger laufen als ihr
Abstand. Ohne Sperre startete beat einen zweiten Lauf, der dieselben Einträge bearbeitete
(doppelt verteilte Verteilermails). Die Sperre hängt an der Datenbankverbindung: Endet der
Worker oder bricht er ab, gibt PostgreSQL sie frei; eine Ablaufzeit wie bei einer Cache-Sperre
gibt es nicht, und niemand kann eine fremde Sperre löschen.

Schlüssel: zwei 32-Bit-Werte (Namensraum, Prüfsumme des Namens), getrennt von den 64-Bit-
Schlüsseln anderer Sperren (PF-30).
"""

from __future__ import annotations

import functools
import logging
import zlib
from contextlib import contextmanager

from django.db import connection

logger = logging.getLogger(__name__)

NAMESPACE = 0x48554245  # "HUBE"

# Grenze für Datenaufträge (Import, Export, Datenübernahme) und Massenversand (Rundschreiben,
# Termin-Mails): 12 Stunden statt der allgemeinen 3 (CELERY_TASK_SOFT_TIME_LIMIT). Bei Ablauf
# melden Import und Export ihren Auftrag als fehlgeschlagen; Rundschreiben setzt der
# Wiederanlauf (alle 15 Minuten) mit den noch wartenden Empfängern fort.
LONG_SOFT = 12 * 60 * 60
LONG_HARD = LONG_SOFT + 60


def _key(name: str) -> int:
    value = zlib.crc32(name.encode())
    return value - 2**32 if value >= 2**31 else value


@contextmanager
def lock(name: str):
    """True, wenn diese Verbindung die Aufgabe ``name`` gerade allein ausführt."""
    key = _key(name)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", [NAMESPACE, key])
        locked = cursor.fetchone()[0]
    try:
        yield locked
    finally:
        if locked:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s, %s)", [NAMESPACE, key])


def einzeln(func):
    """Aufgabe überspringen (Rückgabe None), solange derselbe Job noch läuft."""
    name = f"{func.__module__}.{func.__name__}"

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with lock(name) as locked:
            if not locked:
                logger.info("%s läuft noch, dieser Lauf entfällt", name)
                return None
            return func(*args, **kwargs)

    return wrapper
