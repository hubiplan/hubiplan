"""KI-Schnittstelle Stufe 0 (docs/mcp.md): Hilfe über das Model Context Protocol.

Ohne Anmeldung, nur lesen, keine Vereinsdaten. Geprüft werden Protokoll, Werkzeuge,
Sprachen und die Schutzregeln (Origin, Größe, Drosselung, Abschalten).
"""

import json

import pytest
from django.test import Client

from mcpserver import help_index

pytestmark = pytest.mark.django_db
URL = "/api/mcp/"
HEADERS = {"HTTP_ACCEPT": "application/json, text/event-stream"}


def rpc(client, method, params=None, msg_id=1, **headers):
    body = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        body["params"] = params
    return client.post(URL, json.dumps(body), content_type="application/json", **HEADERS, **headers)


def call(client, tool, **arguments):
    r = rpc(client, "tools/call", {"name": tool, "arguments": arguments})
    assert r.status_code == 200
    result = r.json()["result"]
    return result["content"][0]["text"], result["isError"]


@pytest.fixture
def anon():
    return Client()


def test_initialisieren_und_werkzeuge(anon):
    r = rpc(anon, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
    assert r.status_code == 200
    assert r["Cache-Control"] == "no-store"
    result = r.json()["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert result["capabilities"] == {"tools": {"listChanged": False}}
    assert result["serverInfo"]["name"] == "hubiplan-hilfe"
    # Unbekannte Fassung: wir nennen die neueste
    r = rpc(anon, "initialize", {"protocolVersion": "1999-01-01"})
    assert r.json()["result"]["protocolVersion"] == "2025-11-25"
    # Benachrichtigung: keine Antwort
    r = anon.post(
        URL,
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        content_type="application/json",
    )
    assert r.status_code == 202 and r.content == b""
    tools = rpc(anon, "tools/list").json()["result"]["tools"]
    assert [t["name"] for t in tools] == [
        "hilfe_suchen",
        "hilfe_lesen",
        "hilfe_uebersicht",
        "begriff_erklaeren",
    ]
    for tool in tools:
        assert tool["annotations"]["readOnlyHint"] is True
        assert tool["annotations"]["destructiveHint"] is False
        assert tool["inputSchema"]["type"] == "object"
        assert isinstance(tool["description"], str) and tool["description"]
    assert rpc(anon, "ping").json()["result"] == {}


def test_suchen_lesen_uebersicht(anon):
    text, error = call(anon, "hilfe_suchen", frage="Passwort ändern")
    assert not error
    assert text.startswith("1. Passwort ändern (Name: passwort-aendern)")
    assert "http://testserver/hilfe/passwort-aendern" in text

    text, error = call(anon, "hilfe_lesen", name="passwort-aendern")
    assert not error and text.startswith("# Passwort ändern")
    assert "bild:" not in text  # Bilder nur als Alternativtext
    assert "(Bild: " in text

    text, error = call(anon, "hilfe_lesen", name="seite/mein-konto")
    assert not error and "/hilfe/seite/mein-konto" in text

    text, error = call(anon, "hilfe_uebersicht", art="seiten")
    assert not error and "(seite/mein-konto)" in text
    assert len(text.splitlines()) == sum(1 for e in help_index.help_entries() if e.kind == "page")


def test_englisch(anon):
    text, error = call(anon, "hilfe_lesen", name="passwort-aendern", sprache="en")
    assert not error and text.startswith("# Change your password")
    assert "Guide · " in text and "(Image: " in text
    text, error = call(anon, "hilfe_lesen", name="gibt-es-nicht", sprache="en")
    assert error and text.startswith("This guide does not exist")


def test_begriffe(anon):
    text, error = call(anon, "begriff_erklaeren", begriff="SEPA-Mandat")
    assert not error and text.startswith("## SEPA-Mandat")
    assert "http://testserver/hilfe/begriffe" in text
    text, _ = call(anon, "begriff_erklaeren", begriff="SEPA mandate", sprache="en")
    assert "SEPA mandate" in text


def test_platzhalter_gefuellt():
    # {pl} usw. stehen in den Texten mit den Standardwörtern
    for lang in help_index.LANGS:
        for entry in help_index.help_entries(lang):
            assert "{pl}" not in entry.body and "{sg}" not in entry.body, entry.slug


def test_fehlerhafte_eingaben(anon):
    text, error = call(anon, "hilfe_suchen")
    assert error and "fehlt" in text
    text, error = call(anon, "hilfe_suchen", frage="x" * 201)
    assert error
    text, error = call(anon, "hilfe_suchen", frage="Termin", sprache="fr")
    assert error
    text, error = call(anon, "hilfe_suchen", frage="Termin", anzahl="viele")
    assert error
    text, error = call(anon, "hilfe_suchen", frage="qqqxyz")
    assert not error and "Keine passende Anleitung" in text

    r = rpc(anon, "tools/call", {"name": "mitglieder_loeschen", "arguments": {}})
    assert r.json()["error"]["code"] == -32602
    assert rpc(anon, "resources/list").json()["error"]["code"] == -32601
    r = anon.post(URL, "{kaputt", content_type="application/json")
    assert r.status_code == 400 and r.json()["error"]["code"] == -32700
    r = anon.post(
        URL,
        json.dumps([{"jsonrpc": "2.0", "id": 1, "method": "ping"}]),
        content_type="application/json",
    )
    assert r.json()["error"]["code"] == -32600
    r = rpc(anon, "ping", HTTP_MCP_PROTOCOL_VERSION="2024-01-01")
    assert r.status_code == 400


def test_schutz(anon, settings):
    # Kein Ereignisstrom und keine Sitzungen
    assert anon.get(URL).status_code == 405
    assert anon.delete(URL).status_code == 405
    # Fremde Webseite im Browser (DNS-Rebinding): abgelehnt; eigene Adresse geht
    assert rpc(anon, "ping", HTTP_ORIGIN="https://boese.example").status_code == 403
    assert rpc(anon, "ping", HTTP_ORIGIN="http://testserver").status_code == 200
    # Zu groß
    big = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {"x": "a" * 70000}})
    assert anon.post(URL, big, content_type="application/json").status_code == 413
    # Abschaltbar durch den Betreiber
    settings.MCP_HILFE_ENABLED = False
    assert rpc(anon, "ping").status_code == 404


def test_drosselung(anon, monkeypatch):
    monkeypatch.setattr("mcpserver.views.RATE_LIMIT", 3)
    codes = [rpc(anon, "ping").status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]


def test_keine_daten_aus_der_datenbank(django_assert_num_queries):
    # Die Werkzeuge fragen die Datenbank nie ab (Stufe 0: keine Vereinsdaten)
    from mcpserver import protocol

    def link(slug):
        return f"https://hp.example/hilfe/{slug}"

    with django_assert_num_queries(0):
        for name, args in (
            ("hilfe_suchen", {"frage": "Mitglied aufnehmen"}),
            ("hilfe_lesen", {"name": "mitglied-aufnehmen"}),
            ("hilfe_uebersicht", {}),
            ("begriff_erklaeren", {"begriff": "Mitgliedsart"}),
        ):
            msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call"}
            msg["params"] = {"name": name, "arguments": args}
            assert protocol.handle(msg, link)["result"]["isError"] is False
