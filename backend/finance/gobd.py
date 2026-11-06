"""Ausnahme vom Datenbankschutz festgeschriebener Buchungen (Migration finance/0024).

Nur für das ausdrückliche Löschen einer ganzen Einheit (Plattform, Demodaten); gilt bis
zum Ende der laufenden Transaktion.
"""

from contextlib import contextmanager

from django.db import connection


@contextmanager
def erasure():
    if not connection.in_atomic_block:
        raise RuntimeError("Nur innerhalb einer Transaktion.")
    with connection.cursor() as cur:
        cur.execute("SELECT set_config('app.gobd_erasure', 'on', true)")
    try:
        yield
    finally:
        with connection.cursor() as cur:
            cur.execute("SELECT set_config('app.gobd_erasure', '', true)")
