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

**Regel:** Fachlogik steht nicht in Views. Abläufe, die mehrere Objekte zusammen ändern,
Berechnungen und alles, was auch eine Hintergrundaufgabe, die App-Schnittstelle oder die
MCP-Schnittstelle braucht, gehören in `services.py` oder ein Fachmodul des Bereichs. So lässt
es sich ohne HTTP testen und wiederverwenden.

Die View bleibt der Ort für die Klammer um den ganzen Vorgang: Eine ändernde View-Methode
läuft in einer Transaktion (`@transaction.atomic`), damit Fachänderung und Protokolleintrag
gemeinsam gespeichert werden oder gar nicht. Dienste prüfen keine Rechte; sie bekommen die
Organisation übergeben und werden nur von Stellen aufgerufen, die Rechte und Zeilenschutz
schon geprüft haben.

Jede Anfrage innerhalb einer Organisation läuft über `core/api_base.py` (`OrgScopedMixin`):
Organisation laden, Rechte prüfen, erst dann den Zeilenschutz der Datenbank setzen.

### Schichten

Von unten nach oben; eine Schicht importiert nur gleiche und tiefere:

| Schicht | Bereiche | Inhalt |
| --- | --- | --- |
| Kern | `core` | Mandantentrennung, Verschlüsselung, Dateien, gemeinsame Bausteine |
| Grundlagen | `organizations`, `accounts`, `access`, `audit` | Einheiten, Konten, Rechte, Protokoll |
| Fachmodule | alle übrigen | Mitglieder, Kasse, Termine … |
| Zusammenführung | `config`, `datatransfer`, `demodaten`, `mcpserver`, `partnerapi` | Adressen, Schnittstellen nach außen, Datenübernahme, Demovereine |

Braucht eine tiefere Schicht etwas aus einer höheren, meldet sich die höhere bei ihr an
(Verzeichnis, Signal, Rückruf), statt dass die tiefere sie importiert.

### Wächter

`backend/tests/test_architektur.py` hält den heutigen Stand der Importe gegen die
Schichtrichtung fest (`backend/tests/data/architektur_stand.json`): Es dürfen keine neuen
dazukommen.

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

### Dateigröße

Dateien unter `pages/` und `components/` haben höchstens 800 Zeilen
(`src/test/Dateigroesse.test.ts`, ohne Ausnahmen). Geteilt wird nach Zugehörigkeit: Eine
Komponente, die andere Dateien benutzen, steht in einer Datei mit ihrem Namen und nimmt mit, was
nur sie braucht. Was mehrere Dateien eines Bereichs brauchen, steht bei Komponenten in einer
eigenen Datei, bei Funktionen, Typen und Konstanten in `<bereich>Helpers.ts`. Wird eine einzelne
Komponente zu groß, kommen Zustand und Abläufe in einen Hook (`use<Name>.ts`) und große Teile der
Darstellung in eigene Komponenten.

### Stammdaten gemeinsam laden

Einstellungen und Auswahllisten, die viele Seiten brauchen (Kasseneinstellungen, Konten,
Kategorien, Mitgliedsarten, Untereinheiten), lädt `components/masterData.ts` über den
gemeinsamen Zwischenspeicher `useShared` (`components/shared.ts`): Beim Seitenwechsel sind sie
sofort da, mehrere Bausteine laden sie nur einmal. Der Speicher ist bewusst eng gehalten:

- nur im Arbeitsspeicher der Seite, nie im Browserspeicher;
- nach jeder erfolgreichen ändernden Anfrage, beim Abmelden und beim Kontowechsel leer;
- nach einer Minute wird neu geladen;
- nur für Listen und Einstellungen zum Auswählen, nicht für Personen- oder Finanzdaten.

Alles andere lädt weiter `useLoad` je Seite. Der Server prüft jede Eingabe unabhängig davon.

### Adressen der Schnittstelle

`backend/config/api_routen.json` listet alle Adressen des Servers unter `api/` und `_allauth/`.
Ein Backend-Test hält die Liste aktuell, und `frontend/src/test/ApiAdressen.test.ts` prüft, dass
es jede Adresse gibt, die die API-Schicht aufruft. Wer im Server eine Adresse ergänzt, umbenennt
oder entfernt, erzeugt die Liste neu:

```bash
cd backend && python manage.py api_routen config/api_routen.json
```

### Felder der Antworten

Die Typen der Antworten schreibt die Web-Oberfläche von Hand (`frontend/src/api/*.ts`). Für
Bereiche mit Feldabgleich ruft `backend/tests/feldabgleich.py` die Adressen für den Demoverein
ab und hält echte Antworten in `backend/config/feldabgleich/<bereich>.json` aktuell (dort, weil die
Testumgebung des Servers den Ordner `frontend` nicht sieht). Daraus erzeugt
`frontend/scripts/feldabgleich.mjs` Daten mit Typangabe in
`frontend/src/test/feldabgleich/<bereich>.ts`; `src/test/Feldabgleich.test.ts` prüft, dass sie zu
den Antworten passen. Die Typprüfung der Oberfläche meldet dann jedes
Feld, das der Server liefert und der Typ nicht kennt, jedes Pflichtfeld, das fehlt, und jede
falsche Art. Damit die Antworten jedes Feld zeigen, füllt `backend/tests/feldabgleich_<bereich>.py`
den Demoverein über die Schnittstelle; Felder ohne Beispiel stehen mit Grund in `OHNE_BEISPIEL`.
Bisher abgeglichen: Mitglieder (Arten, Liste, Akte, Ansprechpartner) und Termine (Kategorien,
Liste, Termin, Rückmeldungen, fremde Kalender, Veröffentlichung, Weitergabe). Nach einer Änderung
an diesen Antworten:

```bash
cd backend && FELDABGLEICH_SCHREIBEN=1 pytest tests/test_feldabgleich.py
cd ../frontend && node scripts/feldabgleich.mjs && npm run typecheck
```

### Öffentliche Schnittstelle der Vereinswebseite

Die Vereinswebseite (`hubiplan-website`) liest nur `/api/public/site/v1/…` und testet gegen eine
nachgebildete Schnittstelle. Damit beide zusammenpassen, hält der Server zwei Dateien fest:

- `backend/config/webseite_schnittstelle.json`: welche Felder jede dieser Antworten hat
  (Feldnamen und Arten der Werte, keine Inhalte). Die Webseite prüft ihre Nachbildung dagegen.
- `backend/config/webseite_antworten.json`: die echten Antworten aller Adressen für fünf
  Beispiele (Demoverein, Prüfverein, dessen Vorschau, Demokapelle, leerer Verein). Die Webseite
  zeichnet daraus in ihren Tests jede Seite.

Der Prüfverein (`backend/tests/webseite_pruefverein.py`) ist der Demoverein, in dem jedes Feld
belegt ist und jede Art von Abschnitt vorkommt. `backend/tests/test_webseite_form.py` hält die
Dateien aktuell und schlägt fehl, wenn die Schnittstelle ein Feld liefert, das kein Beispiel
belegt: Ein neues Feld braucht also gleich ein Beispiel im Prüfverein. Wer eine Antwort ändert,
schreibt beide Dateien neu und zieht die Kopien in `hubiplan-website` nach (dort
`scripts/schnittstelle.sh`):

```bash
cd backend && WEBSEITE_SCHNITTSTELLE_SCHREIBEN=1 pytest tests/test_webseite_form.py
```
