# Training und Anwesenheit, Schießnachweis

Modul `training` (Gruppe Vereinsleben, nur Vereine, setzt Mitglieder voraus), Lückenliste
20.11.2026, B1. Code in `backend/training/`, Oberfläche unter Planen › Training und im
Mitgliederbereich unter Training.

## Trainings und Anwesenheit

- Ein **Training** (`TrainingSession`) gehört zum Verein oder zu einer Untereinheit, hat Datum,
  Uhrzeit, Art (Übungsabend, Training, Wettkampf, Sonstiges), Ort, Leitung (freier Text, auch
  Gäste) und eine verschlüsselte Bemerkung. Aus einem Kalendertermin (auch Serien, ±14 Tage)
  lässt sich ein Training übernehmen.
- **Anwesenheit** (`Attendance`) je Mitglied und Training, Quelle `hand` (abgehakt) oder `code`
  (selbst eingecheckt). Zur Auswahl stehen die aktuellen Mitglieder der Einheit.
- **Einchecken per QR-Code**: Die Leitung öffnet das Einchecken; der Code ist ein HMAC über
  Training und 30-Sekunden-Fenster (wie bei Versammlungen) und gilt auch im Fenster davor.
  Link im QR-Code: `/mein-bereich/training/da/<Training>?v=<Verein>&c=<Code>`. Einchecken geht
  nur am Tag des Trainings und am Tag davor oder danach, in Untereinheiten nur für deren
  Mitglieder.
- **Auswertung**: Trainings, Stunden und Teilnahmen je Mitglied im Zeitraum, auch als Excel.
- Rechte `training.view` und `training.edit`; die Migration gibt sie Rollen mit `events.edit`
  (beide) bzw. `events.view` (Ansehen).

## Schießbuch (mit Modul Schießsport)

- Ein Training kann ein **Schießtermin** sein (Disziplin, Kurz- oder Langwaffe, Kaliber,
  erlaubnispflichtig). Jede Anwesenheit erzeugt dann einen bestätigten Eintrag im Schießbuch
  (`ShootingEntry`, Quelle `training`); Austragen löscht ihn wieder.
- Der Vorstand trägt Termine von Hand ein (Quelle `board`, gleich bestätigt). Mitglieder melden
  Termine in anderen Vereinen oder bei Wettkämpfen im Mitgliederbereich (Quelle `member`,
  Status `reported`); sie zählen erst nach Bestätigung. Gemeldete Einträge kann das Mitglied
  zurückziehen.
- Disziplinen: Vorschläge aus einer festen Liste und den bisher verwendeten.

### Auswertung nach § 14 WaffG

`services.evaluate(membership, on)` zählt nur bestätigte Einträge mit erlaubnispflichtigen
Waffen, je Tag höchstens einer je Disziplin. Die Zeiträume zählen vom Prüftag rückwärts.

- **Erwerb (Abs. 3)**: seit mindestens zwölf Monaten Mitglied und in den letzten zwölf Monaten
  entweder in jedem Monat mindestens einmal oder insgesamt mindestens 18-mal.
- **Besitz (Abs. 4)** je Waffenart, letzte 24 Monate: in jedem Quartal mindestens einmal oder in
  beiden Zwölfmonatszeiträumen je mindestens sechsmal. Nach zehn Jahren seit der ersten
  Waffenbesitzkarte genügt die Mitgliedschaft (nur Hinweis).
- Hinweise ohne Rechtswirkung: Pause über vier Monate (BSSB), Mehrheit der Termine in anderen
  Vereinen. Was der Verband anerkennt, entscheidet er; HUBIplan zeigt nur den Stand.

**Bestätigung der Schießtermine (PDF)**: bestätigte Termine der letzten 24 Monate (oder bis zum
Stichtag, wahlweise nur Kurz- oder Langwaffe) mit Stand nach Abs. 3 und 4, Bestätigungstext,
Unterschriftsfeld für den Vorstand nach § 26 BGB und Vereinsstempel; Anlage zum Antrag beim
Verband.

## Datenschutz

- Verarbeitungstätigkeit „training“ im Verzeichnis; Anwesenheit und Schießbuch stehen in der
  Auskunft (`training.json`) und werden beim Vergessen eines Mitglieds gelöscht.
- Die tägliche Aufgabe `training-aufraeumen` löscht Trainings und Einträge nach zehn Jahren
  (Nachweis über zehn Jahre Waffenbesitz).
- Datenübertragung: Trainings, Anwesenheit und Schießbuch gehen mit; Einchecken und der Schlüssel
  dafür sowie die bestätigende Person nicht.

## Schnittstellen

- Verwaltung: `/api/orgs/<Verein>/training/…` und `/api/depts/<Untereinheit>/training/…`
  (Liste mit `?von=&bis=`, `options/`, `report/?format=xlsx`, `<id>/`, `<id>/attendance/`,
  `<id>/checkin/`), Schießbuch nur im Verein: `/api/orgs/<Verein>/shooting-log/…` und
  `/api/orgs/<Verein>/members/<Mitglied>/shooting-log/` samt `pdf/?von=&bis=&waffe=`.
- Mitgliederbereich und App: siehe [app.md](app.md) (`/api/portal/<Zugang>/training/…`).
