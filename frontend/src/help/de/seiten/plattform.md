---
key: page.platform
titel: Plattform
bereich: einstellungen
modul: platform
rechte: [platform.manage]
routen: [/plattform]
stichworte: [Plattform, Verein anlegen, Dachverband, Module freischalten, Selbstupdate]
---

Die Plattform-Verwaltung legt Vereine und Dachverbände auf dieser HUBIplan-Instanz an und schaltet Module frei. Beim Anlegen bekommt eine Person die Rolle „Vorstand“ mit allen Rechten und verwaltet danach selbst Rollen und Benutzer.

Unter Einstellungen legst du die Löschfrist nach dem Austritt fest. Eine kürzere Frist gilt erst 30 Tage nach der Änderung. Bis dahin wird weiter nach der längeren gelöscht, damit ein Tippfehler nicht sofort Daten ehemaliger Mitglieder löscht.

## Neue Versionen

Einmal am Tag fragt HUBIplan bei GitHub nach, ob es ein neueres Release gibt. Dann siehst du oben den Hinweis „Es gibt eine neuere Version von HUBIplan“ mit einem Link auf die Änderungen. Dabei geht nichts über eure Daten an GitHub; GitHub sieht nur die IP-Adresse des Servers, und die Datenschutzerklärung der Plattform erwähnt das. Wer den Server betreibt, schaltet die Prüfung mit `HUBIPLAN_UPDATE_CHECK=0` in der `.env` ab. Was sich geändert hat, steht unter [Neuigkeiten](/hilfe/neuigkeiten), sobald das neue Release läuft.

## Aktualisieren aus HUBIplan (Selbstupdate)

Unter Plattform › Version steht, welche Version läuft und ob es ein neueres Release gibt. Hat der Betreiber das Selbstupdate eingeschaltet (`HUBIPLAN_SELBSTUPDATE=1`, siehe `docs/betrieb.md`), kannst du dort mit „Auf … aktualisieren“ das neue Release einspielen lassen. Dafür brauchst du die Zwei-Faktor-Anmeldung und gibst dein Passwort noch einmal ein.

HUBIplan legt dabei nur einen Auftrag ab. Ein Dienst auf dem Server sichert zuerst die Datenbank, prüft die Signatur des Releases und dass es neuer ist als die laufende Version, und spielt es dann ein. HUBIplan ist dabei einige Minuten nicht erreichbar; die Seite fragt von selbst nach und zeigt danach das Ergebnis. Schlägt etwas fehl, läuft die bisherige Version weiter. Jeder Auftrag steht im Änderungsprotokoll, und der Betreiber bekommt eine Sicherheitsmail.
