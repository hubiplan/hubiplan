# Umfragen und Meinungsbilder

Modul `surveys` (Gruppe Kommunikation, nur Vereine), App `backend/surveys`, Seite `/umfragen`.
Rechte: `surveys.view` und `surveys.edit`, im Verein und in Untereinheiten. Die Migration gibt
beide Rechte allen Rollen, die Termine, Rundschreiben oder Versammlungen bearbeiten dürfen.

Umfragen sind Meinungsbilder, keine Beschlüsse; förmliche Abstimmungen laufen in den
Versammlungen (siehe [versammlungen.md](versammlungen.md)).

## Aufbau

- `Survey`: Titel, Beschreibung, optional Termin, Zielgruppe (`members`, `persons`, `event`,
  `event_yes`), Filter (Untereinheiten, Mitgliedsarten, Vorstand, Alter), Namen (`open`,
  `managers`, `anonymous`), Ergebnis für Befragte (`after_answer`, `always`, `after_close`,
  `managers`), Stand (`draft`, `open`, `closed`), Ende, Erinnerung, Aufbewahrung in Monaten.
- `SurveyQuestion` (höchstens 10): `single`, `multiple`, `yesno`, `dates`, `quantity`, `text`.
- `SurveyOption` (höchstens 30 je Frage): Bezeichnung oder Zeitpunkt, optional Platzzahl.
- `SurveyParticipation`: wer teilgenommen hat (Mitglied, Verwaltung oder Mail-Link).
- `SurveyAnswer`: die Antworten. Bei anonymen Umfragen ohne Verweis auf die Teilnahme, mit
  zufälliger UUID, ohne Zeitstempel; so lässt sich die Antwort niemandem zuordnen.

Titel, Beschreibung, Fragen und Freitexte sind verschlüsselt gespeichert. Alle Tabellen haben
Zeilenschutz (RLS) nach Verein; ein Trigger prüft, dass Untereinheit und Termin zum Verein passen.

## Regeln

- Nach dem Start lassen sich Fragen und Zielgruppe nicht mehr ändern; Namen und Ergebnis nur
  strenger stellen (offen → nur Verwaltung → anonym).
- Anonym: Antworten nicht änderbar, Ergebnis erst ab drei Teilnahmen, kein Eintragen durch die
  Verwaltung, keine Namen in Export und Auskunft.
- Mengenauswahl am Termin: höchstens 1 + Begleitpersonen der Zusage, sonst die eingestellte Zahl.
  Sagt jemand ab, entfernt `events.rsvp.save_response` seine Antworten (`drop_after_decline`).
- Läuft das Ende ab, gilt die Umfrage sofort als beendet; der stündliche Lauf
  (`surveys.tasks.hourly`) setzt den Stand, verschickt Erinnerungen und löscht Antworten mit
  Namen nach der Aufbewahrung (die Zahlen bleiben in `archived`).
- Terminfindung: `POST …/<id>/event/` legt aus einem Vorschlag einen Termin an; Ja-Sager
  übernehmen die Zusage mit `POST /api/portal/<Zugang>/surveys/<id>/follow/`.

## Schnittstellen

- Verwaltung: `/api/orgs/<id>/surveys/` und `/api/depts/<id>/surveys/` mit `options/`,
  `members/`, `count/`, `<id>/`, `<id>/start/`, `close/`, `copy/`, `answers/`, `event/`,
  `export/?datei=pdf|xlsx`.
- Mitgliederbereich und App: `/api/portal/<Zugang>/surveys/` (siehe [app.md](app.md)).
- Mail-Link ohne Anmeldung: `/umfrage/<token>` im Browser, `GET/POST /api/public/survey/<token>/`
  (signiert, gilt bis zum Ende der Umfrage).
- Antworten: Liste je Frage, `{"question": id, "options": [ids]}`, `{"value": "yes"|"no"|"abstain"}`,
  `{"dates": {"<option>": "yes"|"maybe"|"no"}}`, `{"quantities": {"<option>": n}}` oder
  `{"text": "…"}`.

Bescheid beim Start und bei der Erinnerung per Push (`t: "survey"`), sonst per E-Mail mit Link.
Die Auskunft nach Art. 15 DSGVO enthält `umfragen.json` (ohne anonyme Antworten). Bei der
Vollübernahme eines Vereins bleiben Umfragen außen vor: Sie sind kurzlebig und anonyme Antworten
lassen sich keinem Mitglied zuordnen.
