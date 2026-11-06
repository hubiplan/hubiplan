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
| `Resolution` | Beschluss oder Wahl zu einem TOP: Text, Ja/Nein/Enthaltung oder einstimmig, Ergebnis, bei Wahlen Amt und gewählte Person (verschlüsselt, optional Mitgliedschaft), später Nummer im Beschlussbuch |
| `MinutesVersion` | Freigegebenes Protokoll: PDF (privater Speicher), SHA-256, Zeitpunkt, abgelegtes Dokument |
| `Attendance` | Anwesenheit: Mitgliedschaft oder Gast, Name (verschlüsselt), Stand (anwesend, entschuldigt, vertreten), Vertreter |

Leitung, Protokollführung, Notiz sowie Titel und Erläuterung der Tagesordnung sind
verschlüsselt gespeichert. Titel, Zeit und Ort stehen im Termin. RLS trennt nach Organisation;
Untereinheiten trennt die Anwendung über `department`, ein Datenbank-Trigger stellt sicher,
dass Art, Termin und Tagesordnung zur Einheit der Versammlung gehören.

Beim ersten Aufruf legt HUBIplan übliche Arten an (Verein: Jahreshauptversammlung,
außerordentliche Mitgliederversammlung, Vorstandssitzung; Untereinheit: Versammlung, Sitzung
der Leitung). Eine neue Versammlung übernimmt die Tagesordnung der letzten Versammlung
derselben Art oder bekommt eine übliche Tagesordnung.

## Abläufe (Stand V6)

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
- Protokoll (V4): `PATCH` mit `status: held` beendet die Vorbereitung (aus „in Vorbereitung“
  oder „eingeladen“); die Tagesordnung ist dann fest. `PUT …/minutes/` speichert Protokolltext je
  TOP (`AgendaItem.minutes`, verschlüsselt), Beschlüsse und Wahlen sowie Leitung und
  Protokollführung, mit `version` wie die Tagesordnung. Ein TOP ohne `resolutions` lässt seine
  Beschlüsse unverändert. Erstes Speichern setzt den Stand auf „Protokoll in Arbeit“.
- Freigabe (V4): `POST …/minutes/confirm/` mit `role` (`chair` oder `taker`) und `version`
  bestätigt das Protokoll; Leitung und Protokollführung müssen eingetragen sein. Änderungen am
  Protokoll oder an der Anwesenheit heben Bestätigungen auf. Mit der zweiten Bestätigung
  (`meetings/minutes.py`): Beschlussnummern je Einheit und Jahr (`2027/03`), PDF in der Sprache
  der Einheit mit SHA-256 als `MinutesVersion`, Stand „Protokoll freigegeben“, danach keine
  Änderung mehr. Mit Modul `documents` zusätzlich Ablage im Ordner „Protokolle“ der Einheit
  (Sichtbarkeit Vorstand, wird bei Bedarf angelegt; bei vollem Speicher keine Ablage).
  `GET …/minutes/pdf/` liefert das freigegebene PDF oder vorher eine Vorschau als Entwurf.
- Beschlussbuch (V5, `meetings/book.py`): `GET …/resolutions/` listet nummerierte Beschlüsse
  und Wahlen freigegebener Protokolle der Einheit (höchstens 2000), Filter `suche`, `jahr`,
  `art` (Art der Versammlung), `typ` (`resolution`, `election`), `stand` (`open`, `done`,
  `repealed`). Gesucht wird in Python, weil die Texte verschlüsselt sind. `…/resolutions/export/`
  liefert dieselbe Auswahl als Excel. `PATCH …/resolutions/<pk>/` setzt `status`
  (`meetings.edit`). `POST …/resolutions/<pk>/todo/` legt eine eigene Aufgabe mit Beschlusstext
  an (`title`, `due_date` optional; braucht Modul `todos` und `todos.edit`); `Resolution.todo`
  verweist darauf. Private Aufgaben anderer zeigt das Beschlussbuch nur als „Aufgabe angelegt“.
- Mitgliederbereich (V5, `meetings/portal.py`): `GET /api/portal/<zugang>/meetings/` liefert
  eingeladene anstehende Versammlungen mit Tagesordnung und freigegebene Protokolle der letzten
  fünf Jahre, jeweils nur, wenn das Mitglied heute nach der Auswahl der Art stimmberechtigt ist;
  Protokolle nur bei Arten mit `minutes_for = voters`. `…/meetings/<pk>/minutes/` liefert das PDF.
- Anträge (V6): `MeetingKind.motion_days` (Standard 7 bei Mitgliederversammlungen, leer: keine
  Anträge). Eingeladene Stimmberechtigte stellen bis `Beginn − motion_days` im Mitgliederbereich
  Anträge (`POST /api/portal/<zugang>/meetings/<pk>/motions/`, höchstens fünf je Person und
  Versammlung, Titel und Begründung verschlüsselt) und ziehen sie zurück, solange sie eingereicht
  sind (`…/meetings/motions/<pk>/withdraw/`). `POST …/meetings/<pk>/motions/<id>/` mit
  `decision` (`accept` hängt einen Tagesordnungspunkt „Antrag von …“ vom Typ Beschluss an,
  `reject` braucht `reply`) geht in den Ständen „in Vorbereitung“ und „eingeladen“. Anträge
  kommen nur zusammen mit den Mitgliedsdaten in Export und Import und stehen in der Datenauskunft.
- Offen aus V6 (später, Konzept A2): Anwesenheit per App, Online-Abstimmung.
- Wahlen ins Amt (V5, nach dem Rollenumbau): Das Beschlussbuch liefert `elected` (Mitgliedschaft
  der gewählten Person). Im Verein öffnet „Ins Amt übernehmen“ mit Recht `roles.manage` den
  Dialog „Rolle besetzen“ (`AssignRoleDialog`) mit der Rolle gleichen Namens, Beginn am Tag der
  Versammlung und Beenden des Vorgängers; danach setzt die Oberfläche den Stand auf umgesetzt.
  Die Bestätigung im Dialog bleibt nötig, Ämter von Untereinheiten laufen über deren Rollen.
- Export und Import nehmen Arten, Versammlungen und Tagesordnungen mit (auch im Export einer
  Untereinheit), ebenso Protokoll und Beschlüsse, die Anwesenheit nur zusammen mit den Mitgliedsdaten.

## Schnittstelle

| Weg | Zweck |
| --- | --- |
| `GET/POST /api/orgs/<id>/meetings/` | Liste, Anlegen (`kind`, `starts_at`, `ends_at`, `title`, `location`, `agenda_from_last`) |
| `GET/PATCH/DELETE …/meetings/<pk>/` | Einzelne Versammlung; `status` nur `cancelled` oder zurück zu `draft` |
| `PUT …/meetings/<pk>/agenda/` | Tagesordnung speichern |
| `POST …/meetings/<pk>/invitation/` | Einladung als Rundschreiben-Entwurf |
| `PUT …/meetings/<pk>/minutes/` | Protokoll, Beschlüsse und Wahlen |
| `POST …/meetings/<pk>/minutes/confirm/` | Protokoll bestätigen (Leitung, Protokollführung) |
| `GET …/meetings/<pk>/minutes/pdf/` | Protokoll als PDF (Entwurf oder freigegeben) |
| `GET/POST …/meetings/<pk>/attendance/`, `DELETE …/attendance/<id>/` | Anwesenheit |
| `GET/POST …/meetings/kinds/`, `PATCH/DELETE …/kinds/<pk>/` | Arten |
| `GET …/meetings/resolutions/` | Beschlussbuch mit Filtern |
| `GET …/meetings/resolutions/export/` | Beschlussbuch als Excel |
| `PATCH …/meetings/resolutions/<pk>/` | Stand der Umsetzung |
| `POST …/meetings/resolutions/<pk>/todo/` | Beschluss als Aufgabe |
| `GET /api/portal/<zugang>/meetings/` | Einladungen und Protokolle im Mitgliederbereich |
| `GET /api/portal/<zugang>/meetings/<pk>/minutes/` | Freigegebenes Protokoll als PDF |
| `POST /api/portal/<zugang>/meetings/<pk>/motions/` | Antrag stellen |
| `POST /api/portal/<zugang>/meetings/motions/<pk>/withdraw/` | Antrag zurückziehen |
| `POST …/meetings/<pk>/motions/<id>/` | Antrag aufnehmen oder ablehnen |
