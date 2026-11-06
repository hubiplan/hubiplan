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

## Einheiten deaktivieren oder löschen

Unter **Einheiten** → **Bearbeiten** kannst du das Häkchen bei „ist aktiv“ entfernen und speichern. Die Daten bleiben erhalten; du kannst die Einheit später wieder aktivieren.

Für das vollständige Löschen wählst du im Bearbeitungsformular **Einheit löschen**, gibst den vollständigen Namen ein und bestätigst mit **Unwiderruflich löschen**. Mitglieder, Rollen, Finanzdaten und gespeicherte Dateien der Einheit werden entfernt. Benutzerkonten bleiben erhalten. Untergeordnete Einheiten musst du vorher löschen oder umhängen. Verhindern Verweise aus anderen Einheiten das Löschen, erscheint eine Fehlermeldung und die Daten bleiben erhalten. Die Löschung wird im Plattformprotokoll vermerkt. Bereits vorhandene Sicherungen werden dadurch nicht verändert.

## Neue Versionen

Einmal am Tag fragt HUBIplan bei GitHub nach, ob es ein neueres Release gibt. Dann siehst du oben den Hinweis „Es gibt eine neuere Version von HUBIplan“ mit einem Link auf die Änderungen. Dabei geht nichts über eure Daten an GitHub; GitHub sieht nur die IP-Adresse des Servers, und die Datenschutzerklärung der Plattform erwähnt das. Wer den Server betreibt, schaltet die Prüfung mit `HUBIPLAN_UPDATE_CHECK=0` in der `.env` ab. Was sich geändert hat, steht unter [Neuigkeiten](/hilfe/neuigkeiten), sobald das neue Release läuft.

## Aktualisieren aus HUBIplan (Selbstupdate)

Unter Plattform › Version steht, welche Version läuft und ob es ein neueres Release gibt. Hat der Betreiber das Selbstupdate eingeschaltet (`HUBIPLAN_SELBSTUPDATE=1`, siehe `docs/betrieb.md`), kannst du dort mit „Auf … aktualisieren“ das neue Release einspielen lassen. Dafür brauchst du die Zwei-Faktor-Anmeldung und gibst dein Passwort noch einmal ein.

HUBIplan legt dabei nur einen Auftrag ab. Ein Dienst auf dem Server sichert zuerst die Datenbank, prüft die Signatur des Releases und dass es neuer ist als die laufende Version, und spielt es dann ein. HUBIplan ist dabei einige Minuten nicht erreichbar; die Seite fragt von selbst nach und zeigt danach das Ergebnis. Schlägt etwas fehl, läuft die bisherige Version weiter. Jeder Auftrag steht im Änderungsprotokoll, und der Betreiber bekommt eine Sicherheitsmail.

## Adressen je Einheit

Unter Einstellungen › **Adressen je Einheit** ordnest du weitere Adressen einer Einheit zu, zum Beispiel `mitglieder.sv-musterstadt.example` dem Schützenverein Musterstadt. Wer HUBIplan über diese Adresse aufruft, sieht auf der Anmeldeseite Name, Farben, Wappen und Symbol der Einheit; nach der Anmeldung ist sie vorausgewählt. Unbekannte Adressen und die Hauptadresse zeigen die Instanz. Links in Mails der Einheit (Einladung, Anmeldelink, Termine, Helferdienste, Aufgaben, Ausweis, Fotolink, Rundschreiben) führen auf ihre Adresse, sonst auf die der nächsthöheren Einheit mit eigener Adresse; „Passwort vergessen“ schickt den Link für die Adresse, auf der es angefordert wurde. Ein eigenes Symbol lädt die Einheit unter Einstellungen › Erscheinungsbild hoch; ohne eigenes nimmt HUBIplan ihr Wappen. Die Anmeldung gilt je Adresse. Die Adresse muss per DNS auf den Server zeigen und dort als erlaubte Adresse eingetragen sein (`DJANGO_ALLOWED_HOSTS`, Zertifikat). Nextcloud, App-Verbindung und Verbund bleiben bei der Hauptadresse.
