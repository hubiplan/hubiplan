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

Leitung, Protokollführung, Notiz sowie Titel und Erläuterung der Tagesordnung sind
verschlüsselt gespeichert. Titel, Zeit und Ort stehen im Termin. RLS trennt nach Organisation;
Untereinheiten trennt die Anwendung über `department`, ein Datenbank-Trigger stellt sicher,
dass Art, Termin und Tagesordnung zur Einheit der Versammlung gehören.

Beim ersten Aufruf legt HUBIplan übliche Arten an (Verein: Jahreshauptversammlung,
außerordentliche Mitgliederversammlung, Vorstandssitzung; Untereinheit: Versammlung, Sitzung
der Leitung). Eine neue Versammlung übernimmt die Tagesordnung der letzten Versammlung
derselben Art oder bekommt eine übliche Tagesordnung.

## Abläufe (Stand V1)

- Anlegen erzeugt den Termin. Mitgliederversammlungen sind für Mitglieder sichtbar,
  Vorstandssitzungen nur für den Vorstand.
- Die Detailseite zeigt den letzten Tag für die Einladung (Beginn minus Frist der Art) und
  warnt, wenn er verstrichen ist.
- Die Tagesordnung wird als Ganzes gespeichert (`PUT …/agenda/` mit `version`); ein veralteter
  Stand ergibt 409.
- Absagen markiert den Termin als abgesagt. Löschen ist nur in Vorbereitung oder nach einer
  Absage möglich und löscht den Termin mit. Im Kalender lässt sich der Termin einer
  Versammlung nicht löschen.
- Export und Import nehmen Arten, Versammlungen und Tagesordnungen mit (auch im Export einer
  Untereinheit).

## Schnittstelle

| Weg | Zweck |
| --- | --- |
| `GET/POST /api/orgs/<id>/meetings/` | Liste, Anlegen (`kind`, `starts_at`, `ends_at`, `title`, `location`, `agenda_from_last`) |
| `GET/PATCH/DELETE …/meetings/<pk>/` | Einzelne Versammlung; `status` nur `cancelled` oder zurück zu `draft` |
| `PUT …/meetings/<pk>/agenda/` | Tagesordnung speichern |
| `GET/POST …/meetings/kinds/`, `PATCH/DELETE …/kinds/<pk>/` | Arten |
