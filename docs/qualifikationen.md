# Qualifikationen mit Ablaufdatum

Modul `qualifications` („Qualifikationen“, Gruppe Mitglieder, für Vereine und Dachverbände mit
eigenen Mitgliedern). Für neue Einheiten eingeschaltet; bestehende Einheiten bekommen es mit der
Migration `qualifications/0002` freigegeben und schalten es unter Einstellungen › Module ein.
App `backend/qualifications`.

## Daten

- **Art** (`QualificationType`) je Einheit, frei gepflegt: Bezeichnung, Beschreibung, übliche
  Gültigkeit in Monaten (leer: unbefristet), Erinnerung Tage vor dem Ablauf (leer: keine), Schalter
  „nur Einsichtsvermerk“. Nichts ist vorgegeben; die Oberfläche bietet Vorschläge (Erste Hilfe,
  Jugendleiter, Übungsleiter, Standaufsicht, Einsicht erweitertes Führungszeugnis). Eingetragene
  Arten lassen sich nur archivieren.
- **Nachweis** (`Qualification`) an der Person, mit Organisation: erworben (bzw. eingesehen) am,
  gültig bis, Bemerkung. Eine Verlängerung ist ein neuer Nachweis; maßgeblich ist je Person und Art
  der am längsten gültige, die übrigen sind Verlauf.
- **Einsichtsvermerk** (z. B. erweitertes Führungszeugnis nach § 72a SGB VIII): nur Tatsache und
  Datum der Einsicht. Eine Bemerkung lehnt die Schnittstelle ab, ein Dokument gibt es nicht. Eine
  Art mit Bemerkungen lässt sich nicht nachträglich zum Einsichtsvermerk machen.
- Zeilenschutz (RLS) je Organisation; ein Auslöser prüft, dass Nachweis und Art zur selben
  Organisation gehören, ein zweiter dasselbe für die Voraussetzung eines Dienstes.

## Stand und Erinnerung

- Stand eines Nachweises: `expired` (Ablauf vor heute), `expiring` (innerhalb der Erinnerungstage,
  ohne eingestellte Erinnerung 60 Tage) oder `valid`.
- Mail an das Mitglied einmal je Nachweis, sobald die Erinnerungstage erreicht sind
  (`qualifications.tasks.send_reminders`, alle sechs Stunden). Nur aktuelle Mitglieder, nur der
  maßgebliche Nachweis (schon verlängert: keine Mail). Ändert sich das Ablaufdatum, wird die
  Erinnerung wieder fällig.
- „Zu erledigen“ (Recht `members.edit`): je Art eine Zeile mit abgelaufenen und bald ablaufenden
  Nachweisen, Link auf die gefilterte Übersicht.

## Helferdienste

Ein Dienst kann eine Art voraussetzen (`Duty.qualification`). Beim Einteilen fehlt sie oder läuft
sie vor dem Ende der Schicht ab: Hinweis `qualification`, mit „Trotzdem einteilen“ geht es dennoch;
an der Einteilung steht `qualification_issue`. Beim Selbsteintragen im Mitgliederbereich sieht das
Mitglied die Voraussetzung und kann sich ohne gültigen Nachweis nicht eintragen. Ist das Modul aus,
wirkt die Voraussetzung nicht.

## Schnittstelle

| Pfad | Zweck | Rechte |
| --- | --- | --- |
| `GET/POST /api/orgs/<id>/qualification-types/`, `…/<pk>/` (PATCH, DELETE), `…/archive/`, `…/restore/`, `…/reorder/` | Arten | lesen jede Rolle, ändern `org.edit` |
| `GET/POST /api/orgs/<id>/members/<m>/qualifications/`, `…/<pk>/` | Nachweise eines Mitglieds (`current` markiert den maßgeblichen) | `members.view` / `members.edit` |
| `GET /api/orgs/<id>/qualifications/?stand=bald&art=<id>` | maßgebliche Nachweise aller aktuellen Mitglieder | `members.view` |
| `GET …/helpers/qualifications/` | wählbare Arten für Dienste (Verein und Untereinheit) | Helferdienste bearbeiten |

## Datenschutz

- Nach dem Austritt löscht die Bereinigung der Mitgliedschaft die Nachweise im Verein, ebenso das
  Löschen des Verlaufs.
- Die Datenauskunft enthält `qualifikationen.json`.
- Die Datenübernahme nimmt Arten und Nachweise mit den Mitgliedsdaten mit.
