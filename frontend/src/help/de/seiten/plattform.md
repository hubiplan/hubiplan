---
key: page.platform
titel: Plattform
modul: platform
rechte: [platform.manage]
routen: [/plattform]
stichworte: [Plattform, Verein anlegen, Dachverband, Module freischalten, Selbstupdate]
---

Die Plattform-Verwaltung legt Vereine und Dachverbände auf dieser HUBIplan-Instanz an und schaltet Module frei. Beim Anlegen bekommt eine Person die Rolle „Vorstand“ mit allen Rechten und verwaltet danach selbst Rollen und Benutzer.

In der Liste der Einheiten steht je Einheit die Zahl der freigeschalteten Module („12 Module“); ein Klick darauf zeigt sie einzeln.

Unter Einstellungen legst du die Löschfrist nach dem Austritt fest. Eine kürzere Frist gilt erst 30 Tage nach der Änderung. Bis dahin wird weiter nach der längeren gelöscht, damit ein Tippfehler nicht sofort Daten ehemaliger Mitglieder löscht.

## Einheiten deaktivieren oder löschen

Unter **Einheiten** → **Bearbeiten** kannst du das Häkchen bei „ist aktiv“ entfernen und speichern. Die Daten bleiben erhalten; du kannst die Einheit später wieder aktivieren.

Gelöscht wird in zwei Stufen:

1. **Stilllegen und Löschung vormerken**: Im Bearbeitungsformular gibst du unter „Einheit löschen“ den vollständigen Namen ein. Die Einheit und alle Untereinheiten darunter werden sofort stillgelegt, niemand kommt mehr hinein, die Daten bleiben erhalten. Solange die Vormerkung gilt, lässt sich die Einheit nicht wieder aktivieren; mit **Vormerkung zurücknehmen** hebst du sie auf.
2. **Endgültig löschen**: frühestens 30 Tage nach der Vormerkung (eine leere Einheit, die nie Mitglieder und keine Finanzdaten hatte, sofort) und erst, wenn die gesetzlichen Aufbewahrungsfristen für Bücher und Belege aller Geschäftsjahre abgelaufen sind (§ 147 AO: Belege 8, Bücher 10 Jahre). Das Formular zeigt, bis wann die Fristen laufen. Eine Löschsperre in einem Geschäftsjahr verhindert das Löschen. Zur Bestätigung gibst du den Namen ein; HUBIplan fragt außerdem nach einem aktuellen Code der Zwei-Faktor-Anmeldung. Hat die Einheit Finanzdaten, trägst du ein, wer die Fristen bestätigt hat (z. B. Kassenprüfer oder Steuerberater).

Beim endgültigen Löschen werden Mitglieder, Rollen, Finanzdaten und gespeicherte Dateien der Einheit und ihrer Untereinheiten entfernt. Benutzerkonten bleiben erhalten. Zugehörige Vereine eines Dachverbands musst du vorher löschen oder umhängen. Verhindern Verweise aus anderen Einheiten das Löschen, erscheint eine Fehlermeldung und die Daten bleiben erhalten. Die Löschung wird im Plattformprotokoll vermerkt und steht auf der Löschliste: Wird später ein älteres Backup eingespielt, löscht HUBIplan die Einheit erneut.

## Neue Versionen

Einmal am Tag fragt HUBIplan bei GitHub nach, ob es ein neueres Release gibt. Dann siehst du oben den Hinweis „Es gibt eine neuere Version von HUBIplan“ mit einem Link auf die Änderungen. Dabei geht nichts über eure Daten an GitHub; GitHub sieht nur die IP-Adresse des Servers, und die Datenschutzerklärung der Plattform erwähnt das. Wer den Server betreibt, schaltet die Prüfung mit `HUBIPLAN_UPDATE_CHECK=0` in der `.env` ab. Was sich geändert hat, steht unter [Neuigkeiten](/hilfe/neuigkeiten), sobald das neue Release läuft.

## Aktualisieren aus HUBIplan (Selbstupdate)

Unter Plattform › Version steht, welche Version läuft und ob es ein neueres Release gibt. Hat der Betreiber das Selbstupdate eingeschaltet (`HUBIPLAN_SELBSTUPDATE=1`, siehe `docs/betrieb.md`), kannst du dort mit „Auf … aktualisieren“ das neue Release einspielen lassen. Dafür brauchst du die Zwei-Faktor-Anmeldung und gibst dein Passwort noch einmal ein.

HUBIplan legt dabei nur einen Auftrag ab. Ein Dienst auf dem Server sichert zuerst die Datenbank, prüft die Signatur des Releases und dass es neuer ist als die laufende Version, und spielt es dann ein. HUBIplan ist dabei einige Minuten nicht erreichbar; die Seite fragt von selbst nach und zeigt danach das Ergebnis. Schlägt etwas fehl, läuft die bisherige Version weiter. Jeder Auftrag steht im Änderungsprotokoll, und der Betreiber bekommt eine Sicherheitsmail.

## Virenprüfung

Ist auf dem Server keine Virenprüfung eingerichtet oder für die Weitergabe abgeschaltet, steht dort ein Hinweis: Rundschreiben-Anhänge und öffentliche Dokumente gehen dann ungeprüft hinaus. Mit eingerichteter Virenprüfung (ClamAV) gibt HUBIplan solche Dateien nur geprüft weiter.

Ist der Virenscanner kurz nicht erreichbar, nimmt HUBIplan hochgeladene Dokumente, Anhänge und Belege trotzdem an, sperrt sie aber, bis der Scanner sie nachgeprüft hat (Quarantäne). Plattform › Version zeigt, wie viele Dateien gerade warten und ob in einer Schadsoftware gefunden wurde; solche Dateien bleiben dauerhaft gesperrt.

## Adressen je Einheit

Im Abschnitt **Adressen je Einheit** der Plattform-Einstellungen ordnest du weitere Adressen einer Einheit zu, zum Beispiel `mitglieder.sv-musterstadt.example` dem Schützenverein Musterstadt. Wer HUBIplan über diese Adresse aufruft, sieht auf der Anmeldeseite Name, Farben, Wappen und Symbol der Einheit; nach der Anmeldung ist sie vorausgewählt. Unbekannte Adressen und die Hauptadresse zeigen die Instanz. Links in Mails der Einheit (Einladung, Anmeldelink, Termine, Helferdienste, Aufgaben, Ausweis, Fotolink, Rundschreiben) führen auf ihre Adresse, sonst auf die der nächsthöheren Einheit mit eigener Adresse; „Passwort vergessen“ schickt den Link für die Adresse, auf der es angefordert wurde.

Ein eigenes Symbol lädt die Einheit unter Einstellungen › Erscheinungsbild hoch; ohne eigenes nimmt HUBIplan ihr Wappen. Die Anmeldung gilt je Adresse. Die Adresse muss per DNS auf den Server zeigen. Ist auf dem Server `HUBIPLAN_ADRESSEN_AUS_LISTE=1` gesetzt, nimmt er eingetragene Adressen ohne weitere Einstellung an und holt das Zertifikat beim ersten Aufruf; sonst muss der Betrieb sie selbst zulassen (`DJANGO_ALLOWED_HOSTS`, Zertifikat). Nextcloud, App-Verbindung und Verbund bleiben bei der Hauptadresse.

## Rückmeldungen zur Hilfe

Unter jeder Anleitung und Seitenhilfe steht „Hat das geholfen?“. Der Reiter **Hilfe** zeigt die Antworten je Hilfetext, die meisten „Nein“ zuerst, mit dem Satz dazu, was gefehlt hat. Gespeichert sind nur Hilfetext, Sprache, Fassung, Antwort, Satz und Tag, keine Person und kein Verein. Nennt ein Satz doch einen Namen, nimmst du ihn mit **Entfernen** heraus; die Antwort bleibt gezählt.

Darunter steht unter **Suchen ohne Treffer**, wonach in der Hilfe gesucht und nichts gefunden wurde, mit Zähler. Eingaben mit Ziffern oder E-Mail-Adressen werden nicht gespeichert.

## Sicherheit: Meldungen des Browsers

HUBIplan gibt jedem Browser Regeln mit, was die Oberfläche laden und ausführen darf (Content-Security-Policy). Verstößt eine Seite dagegen, etwa weil jemand ein fremdes Skript einschleusen wollte, blockiert der Browser den Inhalt und meldet es an die eigene Instanz. Der Reiter **Sicherheit** zeigt diese Meldungen: was blockiert wurde, welche Regel gegriffen hat, auf welcher Seite, wie oft, wann zuerst und zuletzt.

Gespeichert sind nur Regel, blockierte Herkunft (ohne Pfad), Seite (ohne Nummern und Suchwörter) und Tag, keine Person, kein Verein und keine Adresse des Aufrufers. Nichts geht an fremde Dienste.

Die Meldungen sind nicht beglaubigt. Erweiterungen im Browser lösen sie aus, und weil der Browser sie ohne Anmeldung schickt, kann jeder eine schicken. Meldungen aus Erweiterungen verwirft HUBIplan, soweit sie erkennbar sind. So liest du die Liste:

- Ein blockiertes Skript von einer fremden Adresse (Zusatz „Skript“) verdient einen Blick: Auf welcher Seite war es, und kann dort jemand Text mit Code eingegeben haben? Für den ersten solchen Eintrag bekommt der Betreiber eine Sicherheitsmail, höchstens eine am Tag.
- Dieselbe Meldung auf vielen Seiten, kurz nach einem Update, spricht für einen Fehler in HUBIplan selbst. Bitte dem Projekt melden.
- Einzelne Einträge mit fremden Adressen für Bilder oder Schriften stammen meist aus Erweiterungen oder Übersetzungsdiensten im Browser.

Mit **Entfernen** nimmst du einen geklärten Eintrag heraus, mit **Alle entfernen** leerst du die Liste. Meldet ein Browser denselben Verstoß erneut, steht er wieder da. Die Liste fasst höchstens 500 verschiedene Einträge; ist sie voll, werden neue erst nach dem Entfernen wieder aufgenommen.
