"""Rolle der Anwendung in Tests (Gesamtaudit 15.11., AZ-04).

Im Betrieb läuft jede Anfrage in der Rolle ``core.rls.APP_ROLE``; dort greift die
Zeilensicherheit (RLS). Tests arbeiten als Tabelleneigentümer. Damit der Anfrageweg
trotzdem wie im Betrieb geprüft wird, wechselt ``tests/conftest.py`` für jede Anfrage über
den Testclient in diese Rolle und danach zurück.

Der Wechsel läuft über einen rohen psycopg-Cursor an Djangos Abfrageprotokoll vorbei:
``assertNumQueries`` und ``CaptureQueriesContext`` zählen nur, was die Anwendung selbst
abfragt, nicht den Rollenwechsel des Testaufbaus.
"""

from __future__ import annotations

import contextlib

import pytest
from django.db import connection

# Rolle, die nach einer abgebrochenen Transaktion noch wiederherzustellen ist
_OFFEN = "_hubiplan_test_rolle_offen"


def abgebrochen() -> bool:
    """Steht die Verbindung in einer abgebrochenen Transaktion („current transaction is
    aborted“)? Dann nimmt PostgreSQL bis zum Zurückrollen keinen Befehl an."""
    from psycopg.pq import TransactionStatus

    raw = connection.connection
    return raw is not None and raw.info.transaction_status == TransactionStatus.INERROR


def _ausfuehren(sql: str):
    """Ohne Djangos Abfrageprotokoll ausführen (zählt in keiner Abfragezählung)."""
    connection.ensure_connection()
    with connection.connection.cursor() as cur:
        cur.execute(sql)
        return cur.fetchone() if cur.description else None


def aktiv() -> bool:
    return connection.vendor == "postgresql"


def _datenbank_erlaubt() -> bool:
    """pytest-django sperrt die Datenbank in Tests ohne ``django_db`` (RuntimeError)."""
    try:
        connection.ensure_connection()
    except RuntimeError:
        return False
    return True


def rollen() -> tuple[str, str]:
    """(current_user, session_user) der Testverbindung."""
    return _ausfuehren("SELECT current_user, session_user")


def _setzen(rolle: str) -> None:
    current, session = rollen()
    if rolle == session:
        _ausfuehren("RESET ROLE")
    elif rolle != current:
        _ausfuehren(f'SET ROLE "{rolle}"')


def wiederherstellen(rolle: str) -> bool:
    """Stellt ``rolle`` wieder her. In einer abgebrochenen Transaktion geht das nicht; dann
    merkt sich die Verbindung die Rolle für später. Meist ist das gar nicht nötig: Das
    Zurückrollen (Savepoint des Tests oder Ende des Tests) nimmt das ``SET ROLE`` der
    Anfrage mit zurück, weil es nach dem Savepoint bzw. in der Testtransaktion lag."""
    import psycopg

    try:
        ok = not abgebrochen()
        if ok:
            _setzen(rolle)
    except psycopg.Error:
        # z. B. Abbruch zwischen Prüfung und Befehl; die ursprüngliche Ausnahme der
        # Anfrage soll sichtbar bleiben, nicht dieser Folgefehler
        ok = False
    if not ok:
        setattr(connection, _OFFEN, rolle)
    elif hasattr(connection, _OFFEN):
        delattr(connection, _OFFEN)
    return ok


def offene_nachholen() -> None:
    """Rolle nachholen, die nach einer abgebrochenen Transaktion offen blieb."""
    rolle = getattr(connection, _OFFEN, None)
    if rolle is not None and not abgebrochen():
        wiederherstellen(rolle)


def offene_vergessen() -> None:
    """Am Testende verwerfen: Eine abgebrochene Transaktion endet immer mit einem
    Zurückrollen (Savepoint des Tests oder die Testtransaktion selbst), und das nimmt das
    ``SET ROLE`` der Anfrage mit. In den nächsten Test darf nichts davon wandern."""
    if hasattr(connection, _OFFEN):
        delattr(connection, _OFFEN)


@contextlib.contextmanager
def unter_app_rolle():
    """Block in der eingeschränkten Rolle der Anwendung (RLS aktiv), danach zurück zur
    vorherigen Rolle – auch nach Ausnahmen und abgebrochenen Transaktionen."""
    from core.rls import APP_ROLE

    if not aktiv() or not _datenbank_erlaubt() or abgebrochen():
        # Ohne Datenbankzugriff (Test ohne django_db) oder in einer abgebrochenen
        # Transaktion: Die Anfrage scheitert dann an ihrer eigenen ersten Abfrage, mit dem
        # Fehler, den der Test erwartet – nicht an diesem Rollenwechsel.
        yield
        return
    offene_nachholen()
    vorher = rollen()[0]
    _ausfuehren(f'SET ROLE "{APP_ROLE}"')
    try:
        yield
    finally:
        wiederherstellen(vorher)


def ausnahme_grund(node) -> str | None:
    """Begründung, mit der ein Test ohne Rolle der Anwendung anfragt, sonst None.

    Ausnahmen nur über ``@pytest.mark.ohne_app_rolle(grund="…")``; ein leerer Grund gilt
    nicht (tests/test_az04_app_rolle_waechter.py zählt und prüft alle Ausnahmen)."""
    marker = node.get_closest_marker("ohne_app_rolle")
    if marker is None:
        return None
    grund = str(marker.kwargs.get("grund") or "").strip()
    if not grund:
        pytest.fail('@pytest.mark.ohne_app_rolle braucht grund="…"', pytrace=False)
    return grund
