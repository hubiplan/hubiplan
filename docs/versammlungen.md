# Versammlungen und Sitzungen

Die App `backend/meetings` führt Mitgliederversammlungen, Vorstandssitzungen und
Versammlungen von Untereinheiten. Die Weboberfläche liegt unter `/versammlungen`.
Konzept und Ausbaustufen: `konzepte/versammlungen.md` im Projektordner (V1 bis V6).

## Modul und Rechte

- Optionales Modul `meetings`, in der Plattformverwaltung freizuschalten.
- Bereich „Versammlungen“: `meetings.view` (Versammlungen, Tagesordnungen und später
  Protokolle sehen) und `meetings.edit` (anlegen, ändern, absagen, Arten pflegen). Auch für
  Rollen von Untereinheiten; deren Versammlungen liegen unter `/api/depts/<id>/meetings/`.
- Bestehende Rollen erhalten keine zusätzlichen Rechte durch eine Datenmigration.

## Daten

| Modell | Inhalt |
| --- | --- |
| `MeetingKind` | Art mit Voreinstellungen: Grundtyp, Einladungsfrist, Form der Einladung, Stimmberechtigte, Beschlussfähigkeit, Vollmacht, Sichtbarkeit des Protokolls |
| `Meeting` | Versammlung mit genau einem Termin (`events.Event`, geschützt), Stand, Leitung, Protokollführung, Notiz |
| `AgendaItem` | Tagesordnungspunkt mit Nummer, Titel, Art und Erläuterung |
| `Attendance` | Anwesenheit: Mitgliedschaft oder Gast, Name (verschlüsselt), Stand (anwesend, entschuldigt, vertreten), Vertreter |

Leitung, Protokollführung, Notiz sowie Titel und Erläuterung der Tagesordnung sind
verschlüsselt gespeichert. Titel, Zeit und Ort stehen im Termin. RLS trennt nach Organisation;
Untereinheiten trennt die Anwendung über `department`, ein Datenbank-Trigger stellt sicher,
dass Art, Termin und Tagesordnung zur Einheit der Versammlung gehören.

Beim ersten Aufruf legt HUBIplan übliche Arten an (Verein: Jahreshauptversammlung,
außerordentliche Mitgliederversammlung, Vorstandssitzung; Untereinheit: Versammlung, Sitzung
der Leitung). Eine neue Versammlung übernimmt die Tagesordnung der letzten Versammlung
derselben Art oder bekommt eine übliche Tagesordnung.

## Abläufe (Stand V3)

- Anlegen erzeugt den Termin. Mitgliederversammlungen sind für Mitglieder sichtbar,
  Vorstandssitzungen nur für den Vorstand.
- Die Detailseite zeigt den letzten Tag für die Einladung (Beginn minus Frist der Art) und
  warnt, wenn er verstrichen ist.
- Die Tagesordnung wird als Ganzes gespeichert (`PUT …/agenda/` mit `version`); ein veralteter
  Stand ergibt 409.
- Absagen markiert den Termin als abgesagt. Löschen ist nur in Vorbereitung oder nach einer
  Absage möglich und löscht den Termin mit. Im Kalender lässt sich der Termin einer
  Versammlung nicht löschen.
- Einladung (V2): `POST …/invitation/` legt ein Rundschreiben (Art „Vereinsmitteilung“, nicht
  abbestellbar) als Entwurf an, mit Betreff, Text und Tagesordnung. Empfänger: bei
  Mitgliederversammlungen Mitgliedsarten und Mindestalter der Art, bei Vorstandssitzungen
  `board`, bei Sitzungen der Leitung einer Untereinheit deren Rollen; im Dachverband die
  Vorstände der Vereine. Nötig sind `meetings.edit` und das Recht, Rundschreiben zu versenden.
  Geprüft und verschickt wird im Rundschreiben. Sobald es nicht mehr Entwurf ist, setzt ein
  Signal die Versammlung auf „eingeladen“ (`invited_at` = Versandzeit).
- Anwesenheit (V3): `GET …/attendance/` listet die Stimmberechtigten (dieselbe Auswahl wie die
  Einladung, Stand heute) mit ihrem Eintrag und weitere Einträge (Gäste, Nichtstimmberechtigte).
  `POST` trägt ein oder ändert (`membership` oder `name`, `status`, `represented_by`). Vertreten
  nur, wenn die Art Vollmachten erlaubt, und nur durch ein anwesendes stimmberechtigtes Mitglied;
  wer nicht mehr anwesend ist, verliert seine Vollmachten (die Vertretenen gelten als
  entschuldigt). Beschlussfähigkeit: anwesende plus vertretene Stimmberechtigte gegen den Anteil
  bzw. die Mindestzahl der Art. Nötig ist zusätzlich das Leserecht auf Mitglieder; ändern nur mit
  `meetings.edit`, solange die Versammlung nicht abgeschlossen ist.
- Export und Import nehmen Arten, Versammlungen und Tagesordnungen mit (auch im Export einer
  Untereinheit), die Anwesenheit nur zusammen mit den Mitgliedsdaten.

## Schnittstelle

| Weg | Zweck |
| --- | --- |
| `GET/POST /api/orgs/<id>/meetings/` | Liste, Anlegen (`kind`, `starts_at`, `ends_at`, `title`, `location`, `agenda_from_last`) |
| `GET/PATCH/DELETE …/meetings/<pk>/` | Einzelne Versammlung; `status` nur `cancelled` oder zurück zu `draft` |
| `PUT …/meetings/<pk>/agenda/` | Tagesordnung speichern |
| `POST …/meetings/<pk>/invitation/` | Einladung als Rundschreiben-Entwurf |
| `GET/POST …/meetings/<pk>/attendance/`, `DELETE …/attendance/<id>/` | Anwesenheit |
| `GET/POST …/meetings/kinds/`, `PATCH/DELETE …/kinds/<pk>/` | Arten |
