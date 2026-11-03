---
key: page.platform
titel: Plattform
bereich: einstellungen
modul: platform
rechte: [platform.manage]
routen: [/plattform]
stichworte: [Plattform, Verein anlegen, Dachverband, Module freischalten]
---

Die Plattform-Verwaltung legt Vereine und Dachverbände auf dieser HUBIplan-Instanz an und schaltet Module frei. Beim Anlegen bekommt eine Person die Rolle „Vorstand“ mit allen Rechten und verwaltet danach selbst Rollen und Benutzer.

Unter Einstellungen legst du die Löschfrist nach dem Austritt fest. Eine kürzere Frist gilt erst 30 Tage nach der Änderung. Bis dahin wird weiter nach der längeren gelöscht, damit ein Tippfehler nicht sofort Daten ehemaliger Mitglieder löscht.

## Neue Versionen

Einmal am Tag fragt HUBIplan bei GitHub nach, ob es ein neueres Release gibt. Dann siehst du oben den Hinweis „Es gibt eine neuere Version von HUBIplan“ mit einem Link auf die Änderungen. Dabei geht nichts über eure Daten an GitHub; GitHub sieht nur die IP-Adresse des Servers, und die Datenschutzerklärung der Plattform erwähnt das. Wer den Server betreibt, schaltet die Prüfung mit `HUBIPLAN_UPDATE_CHECK=0` in der `.env` ab. Was sich geändert hat, steht unter [Neuigkeiten](/hilfe/neuigkeiten), sobald das neue Release läuft.
