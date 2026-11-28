# Autospeichern, Rückgängig und Papierkorb

## Autospeichern

Bearbeitungsformulare speichern geänderte Felder kurz nach der letzten Eingabe
(`useAutoSave` in `frontend/src/components/forms.ts`, Anzeige `SaveStatus`).
Neuanlagen speichern erst mit „Anlegen“. Ungültige Eingaben bleiben als
Feldfehler stehen. Beim Bearbeiten eines Termins gehen keine Mails mit; die
Änderungs- bzw. Absage-Mail schickt der Knopf im Formular
(`POST …/events/<id>/notify/`).

Schritt 1 umfasst: Mitgliedsakte (Stammdaten, Zusatzfelder), Termine,
Organisation, Erscheinungsbild, Abteilungen, Mitgliedsarten.

Schritt 2 ergänzt: Beitragssätze, Abrechnungseinstellungen, Vereinsbeiträge,
Konten, Buchungen (Bearbeiten), Veranstaltungen (Finanzen), Zusatzfeld-
Definitionen, Kontaktdaten in der Dachverbandsansicht und die Mitgliedsdaten im
Abteilungsbereich.

Schritt 3 (Oktober 2026) ergänzt: Chronik (Regentschaften samt Foto, Würden),
Titel/Datum/Bemerkung von Dokumenten, Name und Farbe von Terminkategorien,
Umbenennen von Finanzkategorien, Entwurf der Datenschutzhinweise der Webseite
(öffentlich erst mit „Veröffentlichen“), Rechnungsentwürfe (neue Posten
bekommen nach dem ersten Speichern ihre ID) und der eigene Name unter „Mein
Konto“. Versammlungen (November 2026): Angaben, Tagesordnung und Protokoll. Tagesordnung
und Protokoll gehen als Ganzes an den Server (mit `version`), sobald jeder Punkt
einen Titel bzw. jeder Beschluss einen Text und jede Wahl Amt und Person hat;
neue Punkte und Beschlüsse übernehmen danach ihre ID. Statuswechsel, Bestätigen
und PDF speichern vorher alles Offene. Ebenso Versammlungsarten,
Geschäftspartner, Material und Räume (mit `version`), Einträge der Musik (Musiker,
Auftritte, Noten, Mappen, Proben, Besetzungsvorlagen, Programmpunkte) und die
persönlichen Musikerinnerungen. „Schließen“ schließt ein Formular erst, wenn alles gespeichert ist; einen eigenen „Fertig“-Knopf gibt es nicht.

November 2026 (UX-Audit VW-22): Orte und Räume unter Einstellungen › Orte sowie in der
Mitgliedsakte vorhandene Ansprechpartner, Erziehungsberechtigte und Rechnungsangaben (die Akte
lädt erst beim „Schließen“ neu).

Regel: Jedes Bearbeitungsformular zeigt entweder den Speicherzustand (`SaveStatus`) mit
„Schließen“ oder genau einen Knopf. Einen Knopf „Speichern“ behält nur, was folgenreich ist,
einen Zeitraum festlegt, etwas neu anlegt oder ein kleiner Dialog ist. Der Test
`frontend/src/test/UxAudit1116Speichern.test.ts` führt die Ausnahmen mit Begründung; die Liste
darf kürzer werden, nicht länger.

Bewusst weiter mit Knopf, weil folgenreich, nicht rückgängig oder ein Versand:
Neuanlagen (auch Rechnungen, SEPA-Mandate, Mitgliedschaftszeiträume, Vorlagen),
Wertung und Programme eines Wettbewerbs (Neuberechnung der Ergebnisse wird bestätigt),
Belegungen (Serien, Überschneidungen), Ausgabe, Rückgabe und Wartung von Ausstattung,
das Probenprogramm (Wahl „dieser Termin“ oder „ganze Serie“),
Rollen und Rechte samt Zeiträumen der Rollenzuordnung, Freigaben im Verbund
(Daten gehen an eine andere Instanz), Mitgliederportal (Änderungsmeldung an
den Vorstand), E-Mail-Adresse und Passwort, Plattformseiten (Löschfrist,
Module, Einheit abschalten wären schon beim Tippen wirksam). Ebenso
Nextcloud (wer sich anmelden darf, Dienstkonto, automatisches Sperren), in der Mitgliedsakte
alles mit Zeitraum oder Wirkung auf Beiträge und Rechnungen (Abteilungszugehörigkeit,
Verleihung einer Ehrung, Qualifikationen, Ende einer Ermäßigung, Zahler im Haushalt) und die
Formulare der Finanzen (Spenden, Auslagen, Kassenprüfung, Anlagen, Haushaltsplan). Die App nutzt
Bearbeiten-Dialoge mit „Speichern“; jede Änderung ist dort rückgängig zu machen.

## Gleichzeitiges Bearbeiten

Bearbeiten zwei Personen denselben Datensatz, darf die zweite nicht stillschweigend den Stand
der ersten überschreiben. Dafür tragen die Datensätze eine Fassung (`version`), die bei jeder
Änderung hochzählt. Wer ändert oder löscht, schickt die Fassung mit, die er geladen hat; passt
sie nicht mehr, antwortet der Server mit 409 und „… wurde inzwischen geändert. Bitte neu
laden.“ Das Formular zeigt die Meldung an, die eigene Eingabe ist nach dem Neuladen noch
einmal zu machen.

- Baustein: `backend/core/versioning.py` (`Versioned`, `check_request`). Modelle erben von
  `Versioned` und nennen `version` in `derived_fields`: Die Fassung steht nicht im
  Änderungsprotokoll, und „Rückgängig“ setzt sie nie zurück (jedes Speichern zählt hoch, auch
  das Zurückspielen).
- `ModelViewSet` mit `AuditMixin`: `version_conflict = gettext_lazy("…")` setzen, dann prüfen
  Ändern und Löschen von selbst. Eigene Ansichten sperren die Zeile, lesen frisch und rufen
  `check_request(request, obj, text)` auf.
- Die Fassung steht in der Antwort (`version`) und kommt im Rumpf zurück (`PATCH`, `DELETE`,
  Aktionen wie `storno/`), bei `DELETE` ohne Rumpf auch als `?version=`.
- Ohne mitgeschickte Fassung prüft der Server nicht. So arbeiten ältere Apps weiter; für sie
  gilt bis zum Update „wer zuletzt speichert, gewinnt“.
- Oberfläche: Das Formular merkt sich die Fassung beim Öffnen und übernimmt nach jedem eigenen
  Speichern die neue aus der Antwort. Eine im Hintergrund neu geladene Liste zählt nicht, denn
  das Formular zeigt weiter den geöffneten Stand.

Mit Fassung: Aufgaben, Material, Pinnwand, Dienstplan, Training, Auslagen, Bestellungen,
Versammlungen, Haushaltsplan, Rechnungsposten, Belegungen, Umfragen, Pflichten, seit November
2026 auch Stammdaten und Kontakt eines Mitglieds (Verein und Abteilungsbereich), Termine
(Ändern, Löschen) und Buchungen im Kassenbuch (Ändern, Löschen, Storno, Aufteilen).

## Rückgängig und Wiederherstellen

- Jede ändernde API-Anfrage ergibt ein Änderungspaket (`changes.ChangeSet`) mit
  den Rohwerten vorher/nachher je Datensatz (`changes.ChangeRecord`), auch für
  alles, was beim Löschen mitgelöscht oder geleert wird. Erfasst werden die Apps
  `members`, `events`, `organizations`, `customfields`, `finance`, `billing`,
  `documents` (`backend/changes/tracking.py`).
- Antwort-Kopfzeilen: `X-Change-Set`, `X-Change-Undoable`, `X-Change-Kind`,
  `X-Change-Label` (URL-kodierte Beschreibung für die Schrittliste).
- `POST /api/orgs/<org>/changes/<id>/undo/` spielt ein Paket zurück; das
  Ergebnis ist wieder ein Paket – dessen Rückgängig ist das Wiederherstellen.
  Wurden die Daten seitdem geändert, kommt 409 mit `can_force`; mit
  `{"force": true}` wird trotzdem zurückgesetzt.
- Im Abteilungsbereich: `POST /api/depts/<abteilung>/changes/<id>/undo/`, nur
  für eigene Änderungen und mit den Rechten der Abteilung.
- Gesperrt (nicht rückgängig zu machen): E-Mails, Importe, Zugänge, Rollen und
  Rechte, Ausweise, Fotos und Dateien, Vereinswechsel, Sammeländerungen.
- Finanzen und Abrechnung sind rückgängig zu machen, außer was rechtlich
  festgeschrieben ist: Belege, Jahresabschlüsse, Zahlungen, Mahnungen,
  SEPA-Mandate und Lastschriftläufe (`BLOCKING_MODELS`), außerdem Buchungen in
  abgeschlossenen Geschäftsjahren sowie festgeschriebene Rechnungen und deren
  Positionen (`lock_reason`). Ist ein Datensatz erst später festgeschrieben
  worden, lehnt das Rückgängig ihn ab (harter Konflikt).
- Fremde Änderungen darf nur zurücknehmen, wer das Änderungsprotokoll sehen
  darf; zusätzlich braucht es das Bearbeitungsrecht für die betroffenen Daten.
- Oberfläche: ↶/↷ in der Kopfleiste (Strg+Z / Strg+Y außerhalb von
  Eingabefeldern); ▾ daneben öffnet die Liste der letzten Schritte, dort wählt
  man, bis zu welchem Schritt zurück- oder wiederhergestellt wird. Die Liste
  (bis 50 Schritte je Verein/Abteilung) übersteht ein Neuladen der Seite
  (sessionStorage, gilt für den Browser-Tab). Hinweis nach Anlegen/Löschen, Rückgängig-Knopf im
  Änderungsprotokoll und im Verlauf der Mitgliedsakte, Reiter „Papierkorb“.

## Aufbewahrung

Pakete werden nach 30 Tagen gelöscht (Celery-Job
`changes.tasks.purge_old_changes`, täglich). Beim Löschen nach Ablauf der
Löschfrist (`purge_membership`) werden alle Pakete mit Daten der Person sofort
entfernt.
