# KI-Schnittstelle (MCP)

Über das **Model Context Protocol** (MCP) kann ein KI-Assistent (Claude, ChatGPT, ein lokales
Modell …) Werkzeuge von HUBIplan aufrufen. Konzept mit allen Stufen: `konzepte/mcp-schnittstelle.md`
im Projektordner. Umgesetzt ist **Stufe 0**: die HUBIplan-Hilfe, ohne Anmeldung und ohne
Vereinsdaten.

## Adresse und Einrichtung

`https://<Instanz>/api/mcp/`, Transport „Streamable HTTP“. Im KI-Assistenten als eigenen
MCP-Server bzw. Connector mit dieser Adresse eintragen, ohne Anmeldung. Caddy leitet `/api/*`
schon ans Backend weiter; eine eigene Regel ist nicht nötig.

Der Betreiber schaltet die Schnittstelle mit `HUBIPLAN_MCP_HILFE=false` ab (dann 404).
Standard: an, weil nur die ohnehin öffentliche Hilfe (Quelltext unter AGPL) herausgeht.

## Werkzeuge

Alle nur lesend (`readOnlyHint`), ohne Nebenwirkung, ohne Datenbankabfrage. `sprache` ist
`de` (Standard) oder `en`; Antworten und Hinweise kommen in dieser Sprache.

| Werkzeug | Eingaben | Antwort |
|---|---|---|
| `hilfe_suchen` | `frage` (bis 200 Zeichen), `sprache`, `anzahl` (1–10, Standard 5) | Treffer mit Titel, Name, Adresse `/hilfe/<Name>` und erstem Absatz |
| `hilfe_lesen` | `name` (z. B. `passwort-aendern`, `seite/mein-konto`; auch der `key`), `sprache` | ganzer Text als Markdown mit Adresse |
| `hilfe_uebersicht` | `art` (`anleitungen` oder `seiten`), `sprache` | alle Titel mit Namen |
| `begriff_erklaeren` | `begriff`, `sprache` | bis zu drei Einträge aus dem Glossar (Begriffe und Entscheidungen) mit Beispiel |

Die Suche wertet Wörter im Titel (6), in den Stichworten (4) und im Text (1); Anleitungen stehen
bei gleicher Wertung vor Seitenhilfen. Platzhalter wie `{pl}` sind mit den Standardwörtern
gefüllt („Abteilungen“), Bildschirmfotos durch ihren Alternativtext ersetzt („(Bild: …)“).
Links im Text (`/mitglieder`) sind Seiten der Instanz. Hinweise und Ansprechpartner der
Einheit („Hinweise bei uns“, „Wer hilft bei uns?“) gehören zu Vereinsdaten und fehlen.

## Protokoll

- JSON-RPC 2.0 über `POST`, je Anfrage genau eine JSON-Antwort (kein Ereignisstrom, keine
  Sitzung, kein `Mcp-Session-Id`). `GET` und `DELETE`: 405.
- Methoden: `initialize`, `ping`, `tools/list`, `tools/call`; Benachrichtigungen (ohne `id`)
  bekommen `202` ohne Inhalt. Andere Methoden: `-32601`, unbekanntes Werkzeug: `-32602`,
  Stapel (Liste von Nachrichten): `-32600`.
- Fassungen `2025-11-25`, `2025-06-18`, `2025-03-26`; eine unbekannte Fassung beim
  `initialize` wird mit der neuesten beantwortet, ein unbekannter Kopf
  `MCP-Protocol-Version` mit 400.
- Fehler eines Werkzeugs (fehlende Eingabe, unbekannte Anleitung) kommen als Ergebnis mit
  `isError: true` und erklärendem Text, damit der Assistent sich korrigieren kann.

## Schutz

- `Origin` muss fehlen oder die eigene Adresse sein (sonst 403): Gegen DNS-Rebinding, wie die
  Spezifikation verlangt. KI-Dienste schicken keinen `Origin`.
- Höchstens 120 Anfragen je Minute und Adresse (429), Anfragen bis 64 KB (413).
- `Cache-Control: no-store`, keine Anmeldung, keine Cookies nötig.

## Hilfe im Backend

Das Backend wird ohne `frontend/` gebaut. Deshalb liegt die Hilfe als Kopie in
`backend/mcpserver/hilfe.json`: die Markdown-Dateien aus `frontend/src/help/de|en` und die
Begriffe und Entscheidungen der Lernhilfen (`frontend/src/learning/content.ts`, englisch über
`learning/en.json`). Erzeugen im Ordner `frontend`:

```bash
node scripts/mcp-hilfe.mjs
```

`src/test/McpHilfe.test.ts` schlägt fehl, wenn die Kopie nicht mehr zur Hilfe passt.
Code: `backend/mcpserver/` (`help_index.py` lesen und suchen, `tools.py` Werkzeuge,
`protocol.py` JSON-RPC, `views.py` Adresse), Tests `backend/tests/test_mcp_hilfe.py`.
