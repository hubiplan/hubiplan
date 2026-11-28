# Hilfe

Die Hilfe beantwortet „Wie mache ich …?“, „Was kann ich auf dieser Seite tun?“ und „Was heißt
dieses Wort?“. Konzept: `konzepte/hilfe-funktion.md` im Projektordner (Schritte H1–H6), Gliederung
nach `konzepte/hilfe-neustruktur.md` (HN1–HN4).

## Bausteine

| Baustein | Wo |
| --- | --- |
| Hilfe-Seite | `/hilfe`: eine Suche über alles und vier Reiter: **Anleitungen** (`/hilfe/anleitungen`, auch `/hilfe`), **Seiten** (`/hilfe/seiten`, alle Seitenhilfen), **Begriffe** (`/hilfe/begriffe`, das Glossar) und **Neuigkeiten** (`/hilfe/neuigkeiten`). Anleitungen und Seiten sind gegliedert wie die Seitenleiste (Gruppe › Menüpunkt), dazu Mein Konto und Plattform am Ende. Menüpunkt „Hilfe“ unten in der Seitenleiste |
| Anleitung oder Seitenhilfe einzeln | `/hilfe/<name>` bzw. `/hilfe/seite/<name>` |
| Hilfe zu dieser Seite | Knopf oben in der Kopfleiste oder Taste `?`: Leiste rechts (schmal: Blatt von unten) mit der Seitenhilfe und den Anleitungen der Seite; Esc schließt |
| Glossar | Reiter „Begriffe“ (`/hilfe/begriffe`, [lernhilfen.md](lernhilfen.md)); `/glossar` leitet mit Anker dorthin weiter |
| Hilfe für Mitglieder | Wer kein Recht außerhalb von Startseite, Mein Bereich und Mein Konto hat, sieht unter „Anleitungen“ statt der ersten Schritte die Fragen aus `MEMBER_TOPICS` (`src/help/extras.ts`) als Kacheln |
| Für dich: erste Schritte | oben auf `/hilfe`: Pakete je Aufgabenbereich (`FIRST_STEP_PACKAGES` in `src/help/extras.ts`), ein Paket erscheint, sobald die Person eine seiner Anleitungen sehen darf; erledigte Pakete sind zugeklappt. Die Haken stehen nur am eigenen Konto (`/api/me/help/`), in der Ansicht als Rolle gesperrt |
| Warum sehe ich das nicht? | Anleitungen, für die ein Recht fehlt (Modul an), erscheinen ausgegraut in der Suche und unter „Häufige Aufgaben“ der Seitenhilfe, mit dem Namen des Rechts und den Rollen, die Rechte vergeben dürfen |
| Wer hilft bei uns? | auf `/hilfe` und in der Seitenhilfe: Ansprechpartner der Einheit (Einstellungen › Organisation, Recht „Organisationsdaten bearbeiten“), sonst die der nächsten Einheit darüber, sonst nur Rollennamen. Nie automatisch Personen |
| Hinweise bei uns | unter einer Anleitung: kurze Hinweise der Einheit und der Einheiten darüber (höchstens 500 Zeichen, mit „Organisationsdaten bearbeiten“ auf der Seite der Anleitung) |
| Zeig es mir | in der Seitenhilfe unter einer Anleitung: hebt auf der Seite das erste Bedienelement hervor, das die Anleitung **fett** nennt; auf `/hilfe/<name>` öffnet es erst die Seite |
| Neuigkeiten | Reiter `/hilfe/neuigkeiten`: oben „Was ist neu“ nach Monaten aus `src/help/neuigkeiten/de.md` und `en.md` (je Monat eine Zeile „November 2026:“, neueste oben, die letzten drei Monate aufgeklappt; bei sichtbaren Neuerungen ergänzen), darunter die Änderungen je Release aus `CHANGELOG.md`/`CHANGELOG.en.md`. `/hilfe/was-ist-neu` leitet dorthin weiter |
| Seitenhilfe: Begriffe | In der Leiste stehen unter „Begriffe auf dieser Seite“ bis zu sechs Glossarbegriffe, deren Name im Text der Seitenhilfe vorkommt; „Mehr zu …“ springt zum Menüpunkt im Reiter „Seiten“ |
| Suche | Alle Wörter müssen vorkommen; gleichbedeutende Wörter zählen mit (`src/help/synonyms.ts`: „Homepage“ findet „Webseite“). Findet nichts alle Wörter, erscheinen bis zu acht Treffer, denen genau ein Wort fehlt, mit Hinweis |
| Hat das geholfen? | unter jeder Anleitung und Seitenhilfe (Hilfe-Seite und Leiste): Ja oder Nein, bei Nein ein freiwilliger Satz „Was hat gefehlt?“. Gespeichert werden nur Hilfetext, Sprache, Fassung, Antwort, Satz und Tag, keine Person, keine Einheit, keine Adresse. In der Ansicht als Rolle ausgeblendet |
| Plattform › Hilfe | Rückmeldungen je Hilfetext, meiste „Nein“ zuerst, mit den Sätzen (einzeln entfernbar), und Suchwörter ohne Treffer mit Zähler |
| App | Mein Konto in der Android- und der iOS-App: „Hilfe und Anleitungen im Browser“ öffnet `/hilfe` der Instanz |

Sichtbar ist nur, was zur Person passt: Das Modul (`modul`) muss freigeschaltet sein und die Person
braucht eines der Rechte (`rechte`) in der gewählten Einheit. In der Ansicht als Rolle gelten die
Rechte der Ansicht ([ansicht-als-rolle.md](ansicht-als-rolle.md)); die Hilfe zeigt dann, was diese
Rolle sieht.

Einträge ohne eigenes Modul hängen an ihrem Bereich (`inReach` in `src/help/content.ts`): Hilfen,
deren Routen alle unter `/mein-bereich` liegen, erscheinen nur mit eigenem Mitgliederbereich oder
eingeschaltetem Modul Mitgliederbereich; unter `/abteilung` nur mit Rolle in einer Untereinheit
oder Modul Mitglieder; unter `/untereinheiten` nur mit dem Menüpunkt; unter
`/finanzen/kassenzaehlung` nur mit dem Zusatz Zählprotokoll. So bleibt die Hilfe in einem reinen
Kassenbuch bei der Kasse.

## Texte pflegen

Jede Anleitung und jede Seitenhilfe ist eine Markdown-Datei, je Sprache eine, mit gleichem Namen:

```
frontend/src/help/de/anleitungen/passwort-aendern.md
frontend/src/help/en/anleitungen/passwort-aendern.md
frontend/src/help/de/seiten/mein-konto.md
```

Kopf (zwischen zwei Zeilen `---`, in beiden Sprachen gleich bis auf `titel` und `stichworte`):

```yaml
key: guide.password            # guide.… (Anleitung) oder page.… (Seitenhilfe, Ordner seiten/)
titel: Passwort ändern
modul: members                 # optional: nur mit diesem Modul
rechte: [members.edit]         # optional: eines davon nötig
routen: [/mein-konto/anmeldung]
reihe: 10                      # optional: Reihenfolge im Menüpunkt (Ablauf), sonst nach Titel
menue: /mein-konto             # optional: Menüpunkt, wenn nicht die erste Route gilt
siehe: [guide.two_factor]     # optional, nur Seitenhilfen: verwandte Anleitungen
stichworte: [Kennwort, vergessen]
```

Wo ein Eintrag in der Hilfe steht, folgt aus seiner ersten Route (oder `menue`) und der
Seitenleiste (`src/help/menu.ts`, `modules.tsx`): `/finanzen/…` steht unter Verwaltung › Finanzen,
`/mein-konto/…` und `/briefvorlage` unter Mein Konto, `/plattform` unter Plattform. Ändert sich
das Menü, zieht die Hilfe mit. Unter Finanzen trennt die Hilfe wie das Menü „Beiträge und
Rechnungen“ (Modul `billing`) von „Kasse und Abschluss“.

Regeln (geprüft von `src/test/Hilfe.test.tsx`):

- Jede Datei gibt es auf Deutsch und Englisch, mit gleichem Kopf und gleichen Bildern.
- Rechte, Routen und Links (`[Text](/mitglieder)`) gibt es wirklich; jede Datei gehört zu einem
  Menüpunkt.
- Knopf- und Feldnamen stehen **fett** und genau so, wie die Oberfläche sie zeigt (deutsch: Schlüssel
  in `src/i18n/en.json`, englisch: deren Werte).
- Höchstens zehn Schritte je Anleitung, jeder ein Satz.
- Seitenhilfen bleiben kurz: Die Einleitung (vor der ersten `## Überschrift`) hat höchstens
  150 Wörter, jeder Abschnitt höchstens 350 (Englisch 170 und 400). Die Leiste zeigt die Einleitung,
  dann die Anleitungen der Seite und die Abschnitte zum Aufklappen; die Hilfe-Seite zeigt ab drei
  Abschnitten eine Inhaltsübersicht. Was über „Was ist das, was mache ich zuerst, was ist wichtig“
  hinausgeht, gehört in einen Abschnitt oder in eine Anleitung.
- Kein Absatz und kein Listenpunkt hat mehr als 120 Wörter.
- `siehe: [guide.fee_run]` im Kopf einer Seitenhilfe nennt verwandte Anleitungen, die nicht zur
  selben Route gehören; sie erscheinen mit unter „Häufige Aufgaben“.
- Ein Eintrag der Neuigkeiten hat höchstens 90 Wörter; die Einzelheiten stehen in der Hilfe.
- Jede Adresse aus dem Menü (`NAV_ROUTES`) steht mit genauer Adresse in einer Seitenhilfe, damit
  Unterseiten nicht die Hilfe der übergeordneten Seite zeigen.
- Die Neuigkeiten eines Monats sind mit `#### Bereich` gegliedert, „Das Wichtigste“ steht oben.
- Platzhalter der Einheit wie `{pl}` (z. B. „Züge“) werden eingesetzt (`org/terms.ts`).
- Wer eine Seite oder einen Ablauf ändert, passt die Hilfe im selben PR an.
- Danach im Ordner `frontend` `node scripts/mcp-hilfe.mjs` ausführen und
  `backend/mcpserver/hilfe.json` mit einchecken: Die KI-Schnittstelle liest die Hilfe aus dieser
  Kopie ([mcp.md](mcp.md)); `src/test/McpHilfe.test.ts` meldet, wenn sie veraltet ist. Dasselbe
  gilt nach Änderungen an den Begriffen der Lernhilfen (`src/learning/content.ts`, `en.json`).

## Bildschirmfotos

Bilder stehen im Text als `![Beschreibung](bild:name)`; die Beschreibung ist der Alternativtext.
Welche Stelle ein Bild zeigt, steht in `frontend/src/help/bilder.json` (Seite, Demozugang, Ausschnitt
als CSS-Auswahl im Inhalt; mit `wurzel`, etwa `header.topbar`, auch außerhalb des Inhalts). Die
Bilder werden nie von Hand gemacht:

```bash
scripts/hilfe-bilder.sh              # alle Bilder
scripts/hilfe-bilder.sh konto-sprache # nur einzelne
HILFE_DUNKEL=/tmp/dunkel scripts/hilfe-bilder.sh # Prüflauf im Dunkelmodus
```

Mit `HILFE_DUNKEL=<Ordner>` entstehen dieselben Stellen im Dunkelmodus (nur Deutsch) in dem genannten
Ordner außerhalb der Hilfe; axe meldet dabei zu geringe Kontraste als `KONTRAST <Bild>: …`. Diese
Bilder dienen nur der Prüfung und werden nicht eingecheckt.

Das Skript läuft nur lokal (Linux/WSL mit Docker), belegt einen Testplatz, startet in Wegwerf-Containern
Datenbank, Backend mit den erfundenen Demodaten (`seed_testdata`, Englisch freigeschaltet) und die
Oberfläche aus dem Arbeitsstand und fotografiert mit Playwright jede Stelle auf Deutsch und Englisch.
Ergebnis: `frontend/public/hilfe-bilder/<sprache>/<name>.png`. Bilder ansehen, dann einchecken. Ändert
sich eine Seite sichtbar, die Bilder dazu neu erzeugen. Der Test meldet fehlende Bilder.

## Angaben der Einheit

`GET/PATCH /api/orgs/<id>/help/` liefert Ansprechpartner (eigene oder geerbte), Hinweise je Anleitung
(`notes`, von oben nach unten), die Rollen mit „Rollen verwalten“ und die Beschriftungen der Rechte;
lesen darf jede Rolle der Einheit, ändern nur „Organisationsdaten bearbeiten“.
`PUT /api/orgs/<id>/help/notes/<guide.key>/` setzt den eigenen Hinweis (leer entfernt ihn). Beides
steht im Änderungsprotokoll und in der Datenübernahme (`help_contacts`, `help_notes`).

## Rückmeldungen und Suchen ohne Treffer

`POST /api/help/feedback/` (`key`, `language`, `helpful`, `comment`) nimmt die Antwort auf „Hat das
geholfen?“ von jeder angemeldeten Person an, höchstens 30 je Stunde und Konto; der Zähler dafür
steht nur im Zwischenspeicher. Der Satz wird nur bei „Nein“ gespeichert (höchstens 300 Zeichen).
`POST /api/help/search-miss/` (`term`, `language`) zählt Suchwörter ohne Treffer: klein geschrieben,
höchstens vier Wörter und 60 Zeichen, nur Buchstaben; Eingaben mit Ziffern oder `@` werden verworfen.
Die Oberfläche meldet eine Suche erst zwei Sekunden nach dem letzten Tastendruck.

Die Tabellen `HelpFeedback` und `HelpSearchMiss` (App `organizations`) haben bewusst keinen Bezug zu
Person, Konto oder Einheit. `GET /api/platform/help-feedback/` liefert der Plattformverwaltung beides;
`DELETE …/comments/<id>/` leert den Satz einer Rückmeldung, `DELETE …/misses/<id>/` entfernt ein
Suchwort.
