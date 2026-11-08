"""Ausnahmen vom Datenbankschutz festgeschriebener Buchungen (Migrationen finance/0024, 0032).

Die Freigabe prüft die Datenbank selbst (Funktionen mit Eigentümerrechten) und gilt nur für
die laufende Transaktion. Die Rolle der Anwendung kann sie nicht anders erzeugen.
"""

import datetime

from django.db import connection


def _call(sql: str, params: list) -> None:
    if not connection.in_atomic_block:
        raise RuntimeError("Nur innerhalb einer Transaktion.")
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cur:
        cur.execute(sql, params)


def release_unit(org_id: int) -> None:
    """Ausdrückliches Löschen einer ganzen Einheit (Plattform, Demodaten)."""
    _call("SELECT finance_gobd_freigeben_einheit(%s)", [org_id])


def release_documents(org_id: int, year: int, start: datetime.date, end: datetime.date) -> None:
    """Belege eines Geschäftsjahrs nach Ablauf der Aufbewahrungsfrist."""
    _call("SELECT finance_gobd_freigeben_belege(%s, %s, %s, %s)", [org_id, year, start, end])
