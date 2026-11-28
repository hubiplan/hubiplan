# Architektur: Aufbau und Regeln

HUBIplan ist ein Server mit Schnittstelle (API) und mehrere eigenständige Oberflächen, die nur
über diese Schnittstelle mit ihm sprechen: die Web-Oberfläche (`frontend/`), die Apps für
Android und iOS und die Vereinswebseite. Dieses Dokument beschreibt den Aufbau von Server und
Web-Oberfläche und die Regeln, die für neuen Code gelten.

## Server (`backend/`)

Django mit Django REST Framework. Jeder Fachbereich ist eine eigene Django-App.

### Aufgaben der Dateien eines Bereichs

| Datei | Aufgabe |
| --- | --- |
| `models.py` | Daten und ihre festen Regeln (Pflichtfelder, Eindeutigkeit) |
| `serializers.py` | Eingaben prüfen, Daten in JSON wandeln |
| `views.py`, `*_views.py` | Rechte prüfen, Eingaben lesen, einen Dienst aufrufen, antworten |
| `services.py`, Fachmodule | Fachlogik: Abläufe, Berechnungen, alles mit eigener Transaktion |
| `tasks.py` | Hintergrundaufgaben; rufen dieselben Dienste auf wie die Views |
| `urls.py` | Adressen des Bereichs, eingebunden in `config/api_urls.py` |

**Regel:** Fachlogik steht nicht in Views. Was eine Datenbanktransaktion öffnet
(`transaction.atomic`), mehrere Objekte zusammen ändert oder auch von einer Hintergrundaufgabe,
der App-Schnittstelle oder der MCP-Schnittstelle gebraucht wird, gehört in `services.py` oder
ein Fachmodul des Bereichs. So lässt es sich ohne HTTP testen und wiederverwenden.

Jede Anfrage innerhalb einer Organisation läuft über `core/api_base.py` (`OrgScopedMixin`):
Organisation laden, Rechte prüfen, erst dann den Zeilenschutz der Datenbank setzen.

### Schichten

Von unten nach oben; eine Schicht importiert nur gleiche und tiefere:

| Schicht | Bereiche | Inhalt |
| --- | --- | --- |
| Kern | `core` | Mandantentrennung, Verschlüsselung, Dateien, gemeinsame Bausteine |
| Grundlagen | `organizations`, `accounts`, `access`, `audit` | Einheiten, Konten, Rechte, Protokoll |
| Fachmodule | alle übrigen | Mitglieder, Kasse, Termine … |
| Zusammenführung | `config`, `datatransfer`, `mcpserver`, `partnerapi` | Adressen, Schnittstellen nach außen, Datenübernahme |

Braucht eine tiefere Schicht etwas aus einer höheren, meldet sich die höhere bei ihr an
(Verzeichnis, Signal, Rückruf), statt dass die tiefere sie importiert.

### Wächter

`backend/tests/test_architektur.py` hält den heutigen Stand fest
(`backend/tests/data/architektur_stand.json`):

- Importe gegen die Schichtrichtung: Es dürfen keine neuen dazukommen.
- Transaktionen in View-Dateien je Bereich: Die Zahl darf nicht steigen.

Der Bestand ist Altlast und wird Bereich für Bereich abgebaut. Wer ihn verbessert, schreibt
ihn neu, damit die Verbesserung hält:

```bash
cd backend && python tests/architektur.py --schreiben
```

## Web-Oberfläche (`frontend/src/`)

React mit TypeScript. Jede Seite hält ihren Zustand selbst; es gibt keine Zustandsbibliothek.

| Ordner | Aufgabe |
| --- | --- |
| `api/` | je Fachbereich Typen und Aufrufe der Schnittstelle, darunter `client.ts` |
| `pages/` | Seiten, nach Fachbereich geordnet |
| `components/` | gemeinsame Bausteine und Hooks (`useLoad`, `useForm`, `useUndo` …) |
| `auth/`, `org/`, `help/`, `learning/` | die vier globalen Zustände (React-Kontexte) |

Seiten rufen die Schnittstelle nur über `api/` auf, nie mit `fetch` direkt.
