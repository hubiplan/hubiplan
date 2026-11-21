# Kacheln der Startseite bei Anlass

Kacheln zeigen auf der Startseite (Verwaltung und Mitgliederbereich) und in den Apps einen
kurzen Stand: Kennzahlen, ein paar Zeilen und einen Verweis. Sie erscheinen von selbst, wenn gerade
etwas ansteht („Anlass“), und bleiben sonst weg. Browser, Android und iOS lesen dieselbe
Schnittstelle; der Server liefert fertige, übersetzte Texte.

## Auswahl je Kachel

| Wert | Bedeutung |
|---|---|
| `auto` („bei Anlass“, Standard) | nur sichtbar, solange ein Anlass besteht |
| `on` („immer“) | immer sichtbar |
| `off` („nie“) | nie sichtbar, auch bei Anlass; der Inhalt wird gar nicht erst berechnet |

Die Wahl liegt am Konto in `home_layout` je Arbeitsbereich (`o<Verein>`, `d<Untereinheit>`,
`p<Mitgliederzugang>`): `shown` für „immer“, `hidden` für „nie“, sonst „bei Anlass“. Ältere
Fassungen, die das Layout ohne `shown` speichern, löschen die Wahl „immer“ nicht. In der
Startseite im Browser steht die Auswahl unter **Startseite anpassen** › **Zeigen**; die Kacheln
lassen sich dort wie die übrigen Blöcke verschieben und verbreitern.

## Schnittstelle

- Verwaltung: `GET/PUT /api/orgs/<Verein>/home-tiles/`, für die Apps
  `GET/PUT /api/app/v1/admin/u/<Einheit>/home-tiles/` (Untereinheiten haben keine Kacheln).
- Mitgliederbereich: `GET/PUT /api/portal/<Zugang>/home-tiles/`.
- `GET` liefert `scope` und `tiles` in fester Reihenfolge, je Kachel `key`, `title`,
  `description`, `state`, `urgent`, `shown` und `content` (`figures` mit `label`/`value`/`tone`,
  `rows` mit `title`/`detail`/`link`/`tone`, `text`, `link`, `link_label`, `reason`).
  `tone` ist leer, `good`, `warn` oder `bad`; Verweise sind Pfade auf der eigenen Instanz.
  `?keys=a,b` beschränkt die Antwort.
- `PUT` mit `{"key": …, "state": "auto|on|off"}` speichert und antwortet wie `GET`. Unbekannte
  oder nicht erlaubte Kacheln: 404, falscher Zustand: 400.
- Es gibt nur Kacheln, für die Modul und Rechte da sind. Fehler beim Aufbau einer Kachel werden
  protokolliert, die übrigen Kacheln kommen trotzdem.

## Kacheln der Verwaltung und ihre Anlässe

| Schlüssel | Inhalt | Anlass | Voraussetzung |
|---|---|---|---|
| `kasse` | Kontostände, offene Forderungen, fällige Lastschrift | Konto im Minus oder Lastschrift fällig | Modul Finanzen, `finance.view` |
| `anmeldungen` | Angemeldet, freie Plätze, Warteliste je Veranstaltung | Veranstaltung in höchstens 14 Tagen | Modul Anmeldungen, `registrations.view` |
| `verein-zahlen` | Mitglieder, Eintritte, Austritte im Geschäftsjahr | Januar (Stichtagsmeldung) | Verein, Modul Mitglieder, `members.view` |
| `belegung` | Belegung der nächsten sieben Tage | heute oder morgen belegt | Modul Belegung, Leserecht |
| `arbeitsstunden` | Soll erfüllt, Ersatzbeitrag | letzte zwei Monate des Geschäftsjahres | Arbeitsstunden aktiv, `billing.view` |
| `haushalt` | Plan und Ist | eine Position über Plan | Modul Finanzen, `finance.view` |
| `umfragen-pinnwand` | Laufende Umfragen mit Rücklauf, neue Beiträge | eine Umfrage läuft | Modul Umfragen oder Pinnwand mit Leserecht |
| `versammlung` | Datum, Einladungsfrist, Anträge | Versammlung in höchstens sechs Wochen | Modul Versammlungen, Leserecht |

## Kacheln im Mitgliederbereich

| Schlüssel | Inhalt | Anlass |
|---|---|---|
| `meine-arbeitsstunden` | geleistet, Soll, offen | noch Stunden offen in den letzten drei Monaten des Geschäftsjahres |
| `umfragen` | Umfragen, die auf eine Antwort warten | mindestens eine unbeantwortete Umfrage |
| `pinnwand` | neue Beiträge | neue Beiträge seit dem letzten Lesen |
| `meine-anmeldungen` | eigene Anmeldungen | eigene Veranstaltung in höchstens sieben Tagen |

Kacheln für Training/Schießnachweis und Sammelbestellungen folgen, sobald die Module dazu da sind.

Code: `backend/hometiles/` (`org_tiles.py`, `portal_tiles.py`), Wahl in
`backend/accounts/home_actions.py`; Browser `frontend/src/components/home/TileCard.tsx`;
Android `ui/KachelnSection.kt`; iOS `HubiplanKern/Kacheln.swift` und `KachelnView.swift`.
