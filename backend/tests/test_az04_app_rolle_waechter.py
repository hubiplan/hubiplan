"""Wächter: Anfragen in Tests laufen in der Rolle der Anwendung (Gesamtaudit 15.11., AZ-04).

Im Betrieb bearbeitet jede Anfrage die Rolle ``core.rls.APP_ROLE`` mit Zeilenschutz (RLS).
``tests/conftest.py`` macht das für jede Anfrage über den Testclient zum Standard; der
Testaufbau bleibt Tabelleneigentümer. Ausnahmen gibt es nur mit
``@pytest.mark.ohne_app_rolle(grund="…")``. Diese Datei prüft, dass das so bleibt.
"""

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.db import DataError, connection, transaction
from django.test.client import ClientHandler
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from core.rls import APP_ROLE
from core.tenancy import get_rls, reset_rls, set_rls

from . import app_rolle

TESTS = Path(__file__).parent
MARKER = "ohne_app_rolle"

# Tests, deren Anfragen ausnahmsweise als Tabelleneigentümer laufen. Wer eine Ausnahme
# hinzufügt, begründet sie am Test (grund="…") und zählt hier bewusst mit hoch.
ERLAUBTE_AUSNAHMEN = 0

nur_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql", reason="Rollen und RLS gibt es nur in PostgreSQL"
)


def _ausnahmen() -> list[tuple[str, int, str]]:
    """Alle Verwendungen des Markers in tests/: (Datei, Zeile, Begründung oder "")."""
    funde = []
    for datei in sorted(TESTS.rglob("*.py")):
        baum = ast.parse(datei.read_text(encoding="utf-8"))
        aufrufe = set()
        for node in ast.walk(baum):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == MARKER
            ):
                aufrufe.add(id(node.func))
                grund = next((k.value for k in node.keywords if k.arg == "grund"), None)
                text = grund.value if isinstance(grund, ast.Constant) else None
                gueltig = isinstance(text, str) and text.strip() and not node.args
                funde.append((datei.name, node.lineno, text.strip() if gueltig else ""))
        for node in ast.walk(baum):
            # Marker ohne Aufruf (@pytest.mark.ohne_app_rolle) hat keine Begründung
            if isinstance(node, ast.Attribute) and node.attr == MARKER and id(node) not in aufrufe:
                funde.append((datei.name, node.lineno, ""))
    return funde


def test_jede_ausnahme_ist_begruendet():
    ohne_grund = [f"{datei}:{zeile}" for datei, zeile, grund in _ausnahmen() if not grund]
    assert ohne_grund == [], f'{MARKER} braucht grund="…" (als Schlüsselwort): {ohne_grund}'


def test_anzahl_der_ausnahmen_ist_festgeschrieben():
    funde = _ausnahmen()
    assert len(funde) == ERLAUBTE_AUSNAHMEN, (
        f"{len(funde)} Ausnahmen statt {ERLAUBTE_AUSNAHMEN}; neue Ausnahme bewusst in "
        f"ERLAUBTE_AUSNAHMEN eintragen: {funde}"
    )


def test_marker_gilt_nur_mit_begruendung():
    def node(**kwargs):
        return SimpleNamespace(get_closest_marker=lambda name: SimpleNamespace(kwargs=kwargs))

    assert app_rolle.ausnahme_grund(SimpleNamespace(get_closest_marker=lambda name: None)) is None
    assert app_rolle.ausnahme_grund(node(grund=" Prüft den Eigentümerweg ")) == (
        "Prüft den Eigentümerweg"
    )
    for leer in ({}, {"grund": ""}, {"grund": "  "}, {"grund": None}):
        with pytest.raises(pytest.fail.Exception):
            app_rolle.ausnahme_grund(node(**leer))


@pytest.fixture
def beobachtet(monkeypatch):
    """Rolle innerhalb jeder Anfrage festhalten; ``fehler`` wirft dort auf Wunsch."""
    original = ClientHandler.__call__
    zustand = SimpleNamespace(rollen=[], fehler=None)

    def call(self, environ):
        zustand.rollen.append(app_rolle.rollen()[0])
        if zustand.fehler is not None:
            zustand.fehler()
        return original(self, environ)

    monkeypatch.setattr(ClientHandler, "__call__", call)
    return zustand


def _eigentuemer() -> str:
    return app_rolle.rollen()[1]


@nur_postgres
@pytest.mark.django_db
@pytest.mark.parametrize("art", ["django", "drf"])
def test_anfrage_laeuft_in_der_rolle_der_anwendung(client, beobachtet, art):
    eigentuemer = _eigentuemer()
    assert eigentuemer != APP_ROLE
    assert app_rolle.rollen()[0] == eigentuemer
    c = client if art == "django" else APIClient()
    assert c.get("/api/csrf/").status_code == 200
    assert beobachtet.rollen == [APP_ROLE]
    # Danach wieder Eigentümer: Prüfungen und Testaufbau sehen alle Zeilen
    assert app_rolle.rollen() == (eigentuemer, eigentuemer)


@nur_postgres
@pytest.mark.django_db
def test_rollenwechsel_zaehlt_nicht_mit(client):
    with CaptureQueriesContext(connection) as abfragen:
        assert client.get("/api/csrf/").status_code == 200
    sql = " ".join(q["sql"].upper() for q in abfragen.captured_queries)
    # Die Middleware selbst fragt ab (set_config); das zählt wie im Betrieb mit
    assert "SET_CONFIG" in sql
    for befehl in ("SET ROLE", "RESET ROLE", "CURRENT_USER", "SESSION_USER"):
        assert befehl not in sql


@nur_postgres
@pytest.mark.django_db
def test_rolle_zurueck_nach_ausnahme(client, beobachtet):
    eigentuemer = _eigentuemer()

    def fehler():
        raise RuntimeError("Probe")

    beobachtet.fehler = fehler
    with pytest.raises(RuntimeError, match="Probe"):
        client.get("/api/csrf/")
    assert beobachtet.rollen == [APP_ROLE]
    assert app_rolle.rollen()[0] == eigentuemer


@nur_postgres
@pytest.mark.django_db
def test_rolle_zurueck_nach_abgebrochener_transaktion(client, beobachtet):
    """Ein Datenbankfehler in der Anfrage bricht die Transaktion ab; ``RESET ROLE`` ginge
    dann nicht. Das Zurückrollen des Savepoints nimmt das ``SET ROLE`` mit zurück."""
    eigentuemer = _eigentuemer()

    def fehler():
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 / 0")

    beobachtet.fehler = fehler
    with pytest.raises(DataError), transaction.atomic():
        client.get("/api/csrf/")
    assert not app_rolle.abgebrochen()
    assert app_rolle.rollen()[0] == eigentuemer
    # Die nächste Anfrage arbeitet wieder normal
    beobachtet.fehler = None
    assert client.get("/api/csrf/").status_code == 200
    assert beobachtet.rollen == [APP_ROLE, APP_ROLE]
    assert app_rolle.rollen()[0] == eigentuemer


@nur_postgres
@pytest.mark.django_db(transaction=True)
def test_rolle_zurueck_ohne_testtransaktion(client, beobachtet):
    eigentuemer = _eigentuemer()
    assert client.get("/api/csrf/").status_code == 200

    def fehler():
        raise RuntimeError("Probe")

    beobachtet.fehler = fehler
    with pytest.raises(RuntimeError, match="Probe"):
        client.get("/api/csrf/")
    assert beobachtet.rollen == [APP_ROLE, APP_ROLE]
    assert app_rolle.rollen()[0] == eigentuemer


@nur_postgres
@pytest.mark.django_db
def test_verschachtelter_aufruf_stellt_aeussere_anfrage_wieder_her(tmp_path):
    """Die andere Instanz läuft in Tests verschachtelt auf derselben Verbindung (im Betrieb
    ein echter HTTP-Aufruf). Ihre Middleware setzt den RLS-Kontext zurück; danach müssen
    Rolle und Kontext der äußeren Anfrage wieder gelten (tests/verbund_netz.py)."""
    from .verbund_netz import Net

    net = Net(tmp_path)
    andere = net.add("https://andere.example.invalid")
    eigentuemer = _eigentuemer()

    def pruefen(vorher):
        assert get_rls() == vorher
        assert app_rolle.rollen()[0] == APP_ROLE
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('app.bypass_rls')")
            assert cursor.fetchone()[0] == "on"

    with app_rolle.unter_app_rolle():
        # wie eine äußere Anfrage im Plattformbereich (Bypass für Systemaufgaben)
        set_rls(None, None, bypass=True)
        try:
            vorher = get_rls()
            status, _ = net.get(andere + "/api/csrf/")
            assert status == 200
            pruefen(vorher)
            net.send(andere + "/api/csrf/", {"Content-Type": "application/json"}, b"{}")
            pruefen(vorher)
        finally:
            reset_rls()
    assert app_rolle.rollen()[0] == eigentuemer
