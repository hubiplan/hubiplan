# Fristenkalender für Vereinspflichten

Modul `obligations` (Gruppe Verwaltung), App `backend/obligations`, Seite `/fristenkalender`.
Rechte: `obligations.view` und `obligations.edit`. Nur Vereine und Dachverbände, nur die Einheit
selbst.

## Pflichten

`Obligation` hat Bezeichnung, Hinweis, nächste Frist, Wiederholung in Monaten (leer: einmalig),
Vorlauf der Erinnerung in Tagen und eine zuständige Rolle. Die Zuständigkeit hängt an der Rolle,
nicht an einer Person: Nach einem Vorstandswechsel erinnert HUBIplan die neuen Inhaber.

„Erledigt“ legt einen Nachweis an (`ObligationDone`: Frist, Datum, Vermerk, Konto) und schiebt
die Frist um die Wiederholung weiter; verpasste Fristen werden übersprungen. Einmalige Pflichten
sind danach abgeschlossen. Erledigen darf, wer den Fristenkalender pflegt oder die zuständige
Rolle innehat.

## Vorschläge

`obligations/catalog.py` enthält übliche Pflichten eingetragener, gemeinnütziger Vereine in
Deutschland (Steuererklärung und Freistellungsbescheid, Kassenprüfung, Transparenzregister,
Versicherungen, Bestandsmeldung, Datenschutz, Vorstandsänderung beim Registergericht). Jeder
Verein übernimmt, was passt, und ändert alles frei. Vorschläge mit `registered_only` erscheinen
nur, wenn im Impressum „im Register eingetragen“ gesetzt ist. Neue Vorschläge brauchen die
englische Übersetzung in `locale/en`.

## Erinnerung

`obligations.tasks.send_reminders` läuft stündlich. Je Frist geht einmal eine Mail an die
Inhaber der zuständigen Rolle (ohne Rolle: an alle mit `obligations.edit`), sobald der
Erinnerungszeitraum beginnt. Dieselben Pflichten stehen unter „Zu erledigen“
(`obligations/open_tasks.py`).

## Nach einer Vorstandswahl

`meetings.minutes.release` ruft `obligations.election.after_release` auf. Enthält das
freigegebene Protokoll einer Versammlung der Einheit selbst eine angenommene Wahl in ein Amt,
dessen Rolle „vertritt die Einheit (§ 26 BGB)“ trägt (Vergleich über den Namen; ohne solche
Rolle zählen alle Vorstandsrollen), entsteht die Aufgabe „Vorstandsänderung beim Registergericht
anmelden“ mit Frist 14 Tage nach der Versammlung. Sie ist im Beschlussbuch mit der Wahl verknüpft.

Gesteuert wird das über die Pflicht mit dem Auslöser „Wahl“: Frist in Tagen, zuständige Rolle
(die Aufgabe wird mit ihr geteilt) und Abschalten. Ohne eigenen Eintrag gilt die Vorgabe für
Einheiten, die laut Impressum im Register stehen. Ist das Modul Aufgaben aus, entsteht statt der
Aufgabe eine einmalige Pflicht im Fristenkalender.
