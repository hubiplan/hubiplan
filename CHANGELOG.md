# Änderungen an HUBIplan

Hier stehen die Änderungen je Release, das neueste oben. Versionen heißen `JJJJ.MM.N`
(Jahr, Monat, laufende Nummer im Monat), siehe [docs/releases.md](docs/releases.md).
English: [CHANGELOG.en.md](CHANGELOG.en.md).

<!-- Neue Versionen hier einfügen (scripts/release.sh) -->

## 2026.11.1 (2026-11-22)

Das zweite Release fasst knapp drei Wochen Entwicklung seit 2026.11.0 zusammen (562 Pull Requests).
Die wichtigsten Änderungen stehen hier nach Bereichen; jede einzelne Änderung ist im zugehörigen
Pull Request auf GitHub beschrieben.

### Neu

- **Neue Oberfläche:** sieben Bereiche mit einheitlichem Seitenkopf (Pfad, Überschrift,
  Hauptaktion oben rechts), Schnellsuche (Strg+K), eine Startseite, die zuerst zeigt, was zu
  erledigen ist, und frei wählbare Schnellaktionen und Kacheln. Wer Mitglied ist und im Verein
  mitarbeitet, wechselt oben zwischen „Mein Verein“ und der Verwaltung. Auf dem Handy liegen die
  wichtigsten Bereiche in einer Leiste unten; für Mitglieder gibt es einen Dunkelmodus.
- **Aufgaben:** eigene und geteilte Aufgaben mit Zuständigen, Fristen, Erinnerungen per Mail und
  Push, Anhängen, Serien und Aufgaben über mehrere Einheiten.
- **Anmeldungen mit Teilnahmegebühr:** Tarife, Warteliste, Stornostufen, Zusatzleistungen,
  Anmeldung für Nichtmitglieder, Eintrittskarten mit QR-Code, Einlass und Abendkasse per Handy,
  Namensschilder und Teilnahmebescheinigungen, Sammelanmeldung über den Dachverband und eine
  eigene Veranstaltungsseite auf der Webseite.
- **Weitere Module:** Umfragen und Meinungsbilder, Training mit Anwesenheit und Schießnachweis,
  Sammelbestellungen, Pinnwand, Fristenkalender, Qualifikationen mit Ablaufdatum, Material und
  Infrastruktur mit Buchungskalender, Mietpreis und Rechnung, Helferdienste, Chronik als eigenes
  Modul.
- **Musikvereine:** Musiker und Gäste, Auftritte mit Besetzung, Angeboten und Abrechnung,
  Notenarchiv mit Stimmen, Notenmappen und MusicXML, Proben mit Programmen, Abwesenheiten.
- **Mitglieder:** Organisationen als Mitglieder (mit Ansprechpartnern, Stimme in Versammlungen,
  Firmenlastschrift und gestaffeltem Beitrag), Haushalte, abweichende Rechnungsanschrift, Titel,
  automatische Mitgliedsnummer, Online-Mitgliedsantrag, Kündigung im Mitgliederbereich, Ausweis
  in Google Wallet und Apple Wallet, Stichtagsstatistik als Meldedatei, Glückwünsche zu
  Geburtstagen und Jubiläen.
- **Finanzen:** Umsätze direkt von der Bank abrufen (FinTS), Geschäftspartner, Rechnungseingang
  mit Rechnungspostfach, XRechnung für Leistungen und Mitglieder mit Leitweg-ID, Stornorechnungen,
  Splitbuchung, Pauschalen für Ehrenamtliche, Anlagenverzeichnis, Kassenprüfung,
  Künstlersozialabgabe, Vermögensübersicht, Rücklagen, Haushaltsplan, steuerliche Auswertung,
  vereinfachter Spendennachweis, zweckgebundene Spenden, Auslagen erstatten, Ermäßigung mit
  Nachweis, Arbeitsstunden mit Ersatzbeitrag, anteiliger Beitrag bei Eintritt.
- **Vereinswebseite:** Startseite und Textseiten als Baukasten mit vielen neuen Abschnittsarten
  (u. a. Countdown, Häufige Fragen, Partner), Galerie mit Alben, Kopfbilder, Titelfoto als Bühne,
  Feinabstimmung nach Bereichen der Seite, neue Schriften, Änderungen zuerst als Entwurf mit
  Fassungen, Urheberangaben an Bildern, Belegungsanzeige.
- **Termine:** Orte mit Räumen, Anhänge und Dokumente am Termin, Rundschreiben an alle
  Eingeladenen, Termine aus Outlook, Thunderbird oder dem Telefon anlegen, Vorstands-Abo,
  Abgleich mit dem Kalender der Nextcloud.
- **Versammlungen:** Anwesenheit per QR-Code, Unterpunkte in der Tagesordnung, Wahl direkt ins
  Amt übernehmen.
- **Verbindungen:** Anmelden mit Passkey (Web und Apps), KI-Assistenten (z. B. Claude) mit
  Anmeldung über `/api/mcp/` für Hilfe, Webseite, Erscheinungsbild und Chronik, eine öffentliche
  API für andere Programme mit lesenden und schreibenden Zugängen, tiefere Nextcloud-Anbindung
  (Gruppen, Dateien, Videoraum) und Datenschutz-Werkzeuge unter Verwaltung › DSGVO.
- **Apps:** Vorstände entscheiden in der App über Anträge und Belegungsanfragen und leiten
  Versammlungen; Geschäftspartner nachschlagen; Standzugang für Schießmeister.
- **Hilfe:** Neuigkeiten zu jeder Version unter Hilfe › Neuigkeiten, viele neue Anleitungen und
  Lernhilfen, „Hat das geholfen?“ unter jedem Hilfetext.
- **Selbstbetrieb:** eigener Name, Farben, Logo und Symbol für die Installation, eigene Adressen
  je Verein, Hinweis auf neue Releases und Aktualisieren aus der Plattformverwaltung.

### Verbessert

- Mitgliedsakte, Finanzen, Termin-Dialog, Monatskalender und Wettbewerbe sind übersichtlicher
  gegliedert; Knöpfe, Felder und Rückfragen sind überall einheitlich.
- Angaben in Versammlungen und vielen Dialogen speichern sich automatisch.
- Mitgliederliste, Mitgliedersuche, Kalender und Kalender-Abos sind bei großen Vereinen deutlich
  schneller; HUBIplan lädt beim ersten Öffnen schneller.
- Module lassen sich je Verein und Untereinheit freigeben; ausgeschaltete Module verschwinden
  aus Menüs, Rollen und Einstellungen.
- Das Geburtsdatum ist freiwillig. Viele kleine Verbesserungen aus der Bedienbarkeitsprüfung.

### Behoben

- Die englische Oberfläche ist vollständiger übersetzt.
- Hintergrundaufgaben wie Mailversand starten zuverlässig; große Anhänge kommen auch über den
  Verbund an.
- Datenschutz: Auskunft nach Art. 15 DSGVO vollständig, Widerspruch gegen öffentliche Nennung
  wirkt überall, Löschungen und Anonymisierung erfassen auch SEPA-Mandate und Nextcloud-Konten.
- Weitere Fehler in Startseite, Aufgaben, Dachverband-Export und -Kalender, Finanzauswertungen
  und Anzeige behoben.

### Sicherheit

- Jedes Verwaltungsrecht verlangt die Zwei-Faktor-Anmeldung; heikle Schritte wie vollständige
  Exporte, Rollen vergeben oder endgültiges Löschen verlangen einen frischen Code. Hinweismails
  bei Änderungen an Anmeldung und Passwort.
- Namen und weitere Personendaten sind zusätzlich verschlüsselt gespeichert; Datenschlüssel
  lassen sich je Verein wechseln.
- Festgeschriebene Buchungen, Belege und Kassensperren sind auch in der Datenbank geschützt;
  Kassenprüfer bekommen wöchentlich eine Prüfsumme.
- Geheime Abstimmungen und anonyme Umfragen werden so gespeichert, dass sich Antworten niemandem
  zuordnen lassen.
- Anmeldesperren treffen nur noch den Angreifer; Schutz gegen Übernahme über eine zweite
  E-Mail-Adresse und gegen abgefangene App-Codes; KI-Assistenten sind enger begrenzt.
- Hochgeladene Dateien, Importe und Exporte sind gegen manipulierte Inhalte gehärtet; der
  Virenscanner sperrt bei Ausfall statt abzulehnen.

### Für Betreiber

- Updates ohne Datenbankänderung laufen ohne Unterbrechung. Selbstupdate aus der
  Plattformverwaltung (standardmäßig aus); der tägliche Release-Hinweis lässt sich mit
  `HUBIPLAN_UPDATE_CHECK=0` abschalten. Release-Tags sind signiert.
- Tägliche Hintergrundaufgaben laufen zu festen Nachtzeiten, mit Mail, wenn eine ausbleibt.
- Der technische Admin-Bereich `/admin/` ist standardmäßig aus (`DJANGO_ADMIN_ENABLED`).
- Hinter einem eigenen Proxy muss `HUBIPLAN_PROXY_HOSTS` gesetzt sein.
- Vereine werden in zwei Stufen gelöscht (erst stillgelegt, frühestens 30 Tage später endgültig).
- Die Datensicherung liest die Datenbank mit eigenem, nur lesendem Zugang; restic kann die
  Postfächer mitsichern. Beim Ausrollen wird geprüft, dass der Quellcode öffentlich ist.
- Die Apps prüfen die Mindestversion getrennt für Android und iOS.

Datenbank-Migrationen: 298


## 2026.11.0 (2026-11-03)

Erstes Release von HUBIplan. Es fasst den Stand nach der Veröffentlichung als freie Software
(AGPL) zusammen; ab hier stehen die Änderungen jedes Releases einzeln in dieser Datei.

### Neu

- Mitgliederverwaltung mit Mitgliedschaften, Mitgliedsarten, Zusatzfeldern, Ehrungen,
  Jubiläen, Würden und Ämtern mit Chronik, Mitgliedsausweis, Import und Export
- Rollen mit frei wählbaren Rechten je Einheit (Bereiche mit „kein Zugriff“, „lesen“,
  „bearbeiten“), „Ansicht als Rolle“, Zwei-Faktor-Anmeldung, Anmeldung an der Nextcloud
- Beiträge, Rechnungen, SEPA-Lastschrift, Kasse nach GoBD mit Kontoauszügen und digitalen
  Quittungen, Zuwendungsbestätigungen, Jahresabschluss
- Termine mit Zu- und Absagen, Kalender-Abo und fremden Kalendern (Vereinsplaner, iCal)
- Wettbewerbe und Meldungen, Standmodus, Scheibenkatalog, Live-Tabellen
- Rundschreiben, Mailverteiler, Briefvorlagen, Dokumentenablage, Satzung
- Inhalte der Vereinswebseite mit Chronik als Zeitleiste, Designpaketen und Vorschau
- Schnittstelle für die Android-App, Oberfläche auf Deutsch und Englisch, Hilfe und Lernhilfen
- Die laufende Version steht auf der Seite „Lizenzen“

### Für Betreiber

- Ausrollen mit Rückweg (`deploy/zurueck.sh`), Sperre gegen gleichzeitige Läufe und
  Rollout-Protokoll; Versionen und Releases siehe `docs/releases.md`
- Daten verschlüsselt je Verein, tägliches Backup mit Rücksicherungstest

