# Änderungen an HUBIplan

Hier stehen die Änderungen je Release, das neueste oben. Versionen heißen `JJJJ.MM.N`
(Jahr, Monat, laufende Nummer im Monat), siehe [docs/releases.md](docs/releases.md).
English: [CHANGELOG.en.md](CHANGELOG.en.md).

<!-- Neue Versionen hier einfügen (scripts/release.sh) -->

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

