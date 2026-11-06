# Helferdienste und Schichtpläne

Modul `helpers` (abschaltbar, von der Plattform freigeschaltet), App `backend/helpers`. Konzept
mit den Ausbaustufen H1–H5; dieser Stand ist H2.

## Modul und Rechte

- Bereich `helpers.view` (Pläne und Einteilungen sehen) und `helpers.edit` (Pläne anlegen,
  einteilen). Beide gibt es auch für Rollen von Untereinheiten (`/api/depts/<id>/helpers/`);
  dort sind nur Mitglieder der Untereinheit einteilbar.
- Telefonnummern externer Helfer sieht nur, wer `helpers.edit` hat.

## Daten

| Modell | Inhalt |
| --- | --- |
| `HelperPlan` | Dienstplan: Titel, optional Termin der Einheit, Stand (in Vorbereitung, veröffentlicht, abgeschlossen), Einstellungen (Selbsteintragung, Absagefrist, Höchstzahl Schichten, Namen sichtbar, Erinnerung Tage vorher), Hinweis (verschlüsselt) |
| `Duty` | Dienst mit Ort, Beschreibung, Mindestalter, Reihenfolge |
| `Shift` | Schicht mit Beginn, Ende, Bedarf, Hinweis |
| `ShiftAssignment` | Einteilung: Mitgliedschaft oder externe Person, Name und Telefon verschlüsselt, Herkunft, Stand (eingetragen, abgesagt), geleistet, Zeitpunkt der Erinnerung |

RLS trennt nach Organisation; Untereinheiten trennt die Anwendung über `department`. Ein
Datenbank-Trigger stellt sicher, dass Dienste, Schichten und Einteilungen zur Organisation ihres
Plans gehören und der Termin zur Einheit des Plans.

## Abläufe

- Schichten lassen sich einzeln (`starts_at`, `ends_at`) oder per Schnelleingabe anlegen:
  `day` und `quick` wie „14-18, 18-22, 22-02“; endet ein Zeitfenster vor seinem Beginn, liegt
  das Ende am nächsten Tag.
- Einteilen prüft, ob die Schicht voll ist, ob sich die Person mit einer anderen Schicht
  überschneidet (alle nicht abgeschlossenen Pläne der Organisation) und ob sie das Mindestalter
  des Dienstes am Schichtbeginn erreicht. Treffer kommen als 400 mit `warnings`
  (`full`, `overlap`, `age`); mit `force: true` wird trotzdem eingeteilt.
- Dienste und Schichten mit Eingeteilten lassen sich nicht löschen. Ein abgeschlossener Plan ist
  gesperrt, bis er wieder geöffnet wird; ein veröffentlichter Plan muss vor dem Löschen
  abgeschlossen werden.
- Druck: `GET …/<pk>/export/` liefert den Aushang als PDF (je Dienst eine Seite mit freien
  Zeilen), `?datei=xlsx` die Gesamtliste als Excel.
- Export und Import nehmen Pläne, Dienste und Schichten mit (auch im Export einer
  Untereinheit), die Einteilungen nur zusammen mit den Mitgliedsdaten.

## Schnittstelle

| Weg | Zweck |
| --- | --- |
| `GET/POST /api/orgs/<id>/helpers/` | Liste mit Bedarf und offenen Plätzen, Anlegen |
| `GET/PATCH/DELETE …/helpers/<pk>/` | Plan mit Diensten, Schichten und Einteilungen |
| `POST …/helpers/<pk>/duties/`, `PATCH/DELETE …/duties/<pk>/` | Dienste |
| `POST …/duties/<pk>/shifts/`, `PATCH/DELETE …/shifts/<pk>/` | Schichten |
| `POST …/shifts/<pk>/assignments/`, `PATCH/DELETE …/assignments/<pk>/` | Einteilung |
| `GET …/helpers/members/?suche=` | Mitglieder zum Einteilen (nur Namen, nur `helpers.edit`) |
| `GET …/helpers/events/` | Termine der Einheit zum Verknüpfen |
| `GET …/helpers/<pk>/export/` | Aushang (PDF) oder Liste (`?datei=xlsx`) |

## Mitgliederbereich (H2)

- Mitglieder mit laufender Mitgliedschaft sehen veröffentlichte Pläne des Vereins und der
  Untereinheiten, denen sie angehören. Entwürfe und Pläne fremder Untereinheiten bleiben
  unsichtbar; Namen anderer erscheinen nur, wenn der Plan das erlaubt.
- Selbst eintragen geht nur in Plänen mit Selbsteintragung, vor Schichtbeginn, bis zur
  Höchstzahl je Person und ohne Treffer der Prüfungen aus H1 (voll, Überschneidung,
  Mindestalter); im Mitgliederbereich gibt es kein „trotzdem“.
- Absagen geht bis `cancel_days` Tage vor Schichtbeginn, danach und in abgeschlossenen Plänen
  nur über die Verwaltung. Eine Absage setzt den Stand auf „abgesagt“, die Zeile bleibt.
- „Meine Dienste“ zeigt eigene Schichten in nicht vorbereiteten Plänen ab gestern, auch als
  Kalenderdatei (iCalendar, UTC).
- Erinnerungen: Die Celery-Aufgabe `helpers.tasks.send_reminders` läuft stündlich und schreibt
  jedem eingeteilten Mitglied mit E-Mail-Adresse `remind_days` Tage vor Schichtbeginn eine Mail
  in der Sprache des Vereins. `reminded_at` wird vor dem Senden gesetzt, damit niemand doppelt
  erinnert wird.
- Die Datenauskunft eines Mitglieds enthält `helferdienste.json` (Einteilungen) und
  `versammlungen.json` (Anwesenheit, Wahlen).

| Weg | Zweck |
| --- | --- |
| `GET /api/portal/<zugang>/helpers/` | Sichtbare Pläne und „Meine Dienste“ |
| `POST …/helpers/shifts/<pk>/signup/` | Selbst eintragen |
| `POST …/helpers/assignments/<pk>/cancel/` | Selbst absagen |
| `GET …/helpers/calendar/` | Meine Dienste als `.ics` |

## Nächste Stufen

H3 Kontingente für Untereinheiten; H4 Plan kopieren, Aufruf per
Rundschreiben, geleistete Dienste; H5 Android-App.
