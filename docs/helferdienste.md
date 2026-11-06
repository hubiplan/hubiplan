# Helferdienste und Schichtpläne

Modul `helpers` (abschaltbar, von der Plattform freigeschaltet), App `backend/helpers`. Konzept
mit den Ausbaustufen H1–H5; dieser Stand ist H1.

## Modul und Rechte

- Bereich `helpers.view` (Pläne und Einteilungen sehen) und `helpers.edit` (Pläne anlegen,
  einteilen). Beide gibt es auch für Rollen von Untereinheiten (`/api/depts/<id>/helpers/`);
  dort sind nur Mitglieder der Untereinheit einteilbar.
- Telefonnummern externer Helfer sieht nur, wer `helpers.edit` hat.

## Daten

| Modell | Inhalt |
| --- | --- |
| `HelperPlan` | Dienstplan: Titel, optional Termin der Einheit, Stand (in Vorbereitung, veröffentlicht, abgeschlossen), Voreinstellungen für H2 (Selbsteintragung, Absagefrist, Höchstzahl Schichten, Namen sichtbar), Hinweis (verschlüsselt) |
| `Duty` | Dienst mit Ort, Beschreibung, Mindestalter, Reihenfolge |
| `Shift` | Schicht mit Beginn, Ende, Bedarf, Hinweis |
| `ShiftAssignment` | Einteilung: Mitgliedschaft oder externe Person, Name und Telefon verschlüsselt, Herkunft, Stand (eingetragen, abgesagt), geleistet |

RLS trennt nach Organisation; Untereinheiten trennt die Anwendung über `department`. Ein
Datenbank-Trigger stellt sicher, dass Dienste, Schichten und Einteilungen zur Organisation ihres
Plans gehören und der Termin zur Einheit des Plans.

## Abläufe (Stand H1)

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

## Nächste Stufen

H2 Veröffentlichen mit Selbsteintragung und Absage im Mitgliederbereich, Meine Dienste,
Erinnerungen, Kalenderdatei; H3 Kontingente für Untereinheiten; H4 Plan kopieren, Aufruf per
Rundschreiben, geleistete Dienste; H5 Android-App.
