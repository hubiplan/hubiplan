# Hinweise für die Arbeit an hubiplan

## Projektregeln

- **Nie Tests auf dem Testserver ausführen**, auch keine Test-Container. Tests laufen lokal
  unter Linux/WSL mit Docker und `scripts/test.sh`. Danach darf ausgerollt werden;
  `deploy/deploy.sh` akzeptiert nur lokal getestete Stände.
- **Höchstens drei Testläufe gleichzeitig, jeder höchstens 6 Kerne**, projektübergreifend.
  Tests nur über `scripts/test.sh` starten. Es holt über `scripts/testplatz.sh` einen Platz;
  andere Projekte verwenden `testplatz <befehl>` (siehe [docs/testserver.md](docs/testserver.md)).
- Keine Passwörter, Schlüssel oder Geheimnisse ins Repo, in PRs oder in Chats.
- Persönliche Rechnerpfade, Serverziele, Betriebsunterlagen sowie interne Chat-/Projektlinks
  bleiben in privaten lokalen Unterlagen. Öffentliche Beispiele verwenden Musterwerte.
- Auf Testservern und in Beispielen nur erfundene Personen-, Kontakt- und Finanzdaten.
- **Jeder neue Oberflächentext gleich auch auf Englisch**: `t()` + `src/i18n/en.json`, Backend
  `gettext` + `locale/en`. Siehe [docs/uebersetzung.md](docs/uebersetzung.md).
- **Hilfe mitpflegen**: Bei geänderten Seiten oder Abläufen die Hilfe (`frontend/src/help/`,
  Deutsch und Englisch) im selben PR anpassen. Geänderte Hilfebilder lokal mit
  `scripts/hilfe-bilder.sh` erzeugen (siehe [docs/hilfe.md](docs/hilfe.md)).
- **Jeder PR füllt „Für die Änderungshinweise“** der PR-Vorlage aus (Deutsch und Englisch, Art,
  Migration/Rückweg). Releases und Tags nur auf ausdrückliche Anweisung des Betreuers;
  Migrationen bleiben eine Fassung lang abwärtsverträglich (siehe [docs/releases.md](docs/releases.md)).
- CI (GitHub Actions) läuft nur von Hand (`workflow_dispatch`), ohne automatische Auslöser.

Details: [docs/testserver.md](docs/testserver.md), [docs/betrieb.md](docs/betrieb.md).
