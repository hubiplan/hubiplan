# Testserver

Ein Testserver ist eine getrennte Linux-/Docker-Installation mit ausschließlich erfundenen Daten.
`test.example.org` ist ein Platzhalter. Das tatsächliche SSH-Ziel steht nur lokal in
`~/.config/hubiplan/testserver` (eine Zeile, z. B. `deploy@test.example.org`).

## Aufbau

`docker-compose.server.yml` startet:

| Dienst | Aufgabe |
| --- | --- |
| `web` | Caddy: HTTPS mit Let's-Encrypt-Zertifikat (automatisch), liefert das gebaute Frontend aus und leitet `/api`, `/_allauth`, `/admin`, `/static` ans Backend weiter |
| `backend` | Django mit gunicorn (`DJANGO_DEBUG=false`), führt beim Start die Migrationen aus |
| `worker` | Celery-Worker (Import, Export) |
| `beat` | Zeitplan (Löschfrist täglich) |
| `backup` | tägliches verschlüsseltes Backup mit Rücksicherungstest, siehe [betrieb.md](betrieb.md) |
| `postgres`, `redis` | Datenbank und Nachrichtenvermittlung, von außen nicht erreichbar |

Von außen offen sind nur die Ports 22 (SSH), 80 und 443 (Server-Firewall).

Die Geheimnisse (`DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`) stehen nur in
`/opt/hubiplan/.env` auf dem Server. Beim ersten Ausrollen erzeugt
`deploy/server-setup.sh` sie zufällig. Vorlage: `.env.server.example`.

## Ausrollen

Feste Regeln:

- **Tests laufen nie auf dem Testserver.** Erst lokal testen, dann ausrollen.
- Tests nur über `scripts/test.sh` starten; es holt sich einen lokalen Testplatz
  (siehe „Testplätze“ unten).

Tests und Ausrollen erfolgen aus einem lokalen Linux-/WSL-Klon mit Docker.
Checkout-Pfad, SSH-Programm und Schlüssel werden lokal konfiguriert; `DEPLOY_KEY` ist optional.

```bash
cd ~/hubiplan && git fetch origin && git checkout --detach origin/main
scripts/test.sh                                   # Backend, Frontend; BACKUP_TEST=1 für Backup
DEPLOY_HOST=deploy@test.example.org DEPLOY_SUDO=1 deploy/deploy.sh  # erst nach grünem Testlauf
```

`scripts/test.sh` vermerkt den getesteten Stand (Git-Tree) in
`~/.local/state/hubiplan/tested-trees`. `deploy/deploy.sh` bricht ab, wenn der Stand dort
fehlt. Ein Merge-Commit mit unverändertem Inhalt gilt als getestet.

### Nur geänderte Teile

`scripts/test.sh` merkt sich in `~/.local/state/hubiplan/tested-parts` zusätzlich, welche
Teile mit welchem Inhalt grün waren. Der Schlüssel ist ein Hash über die Dateien, die in
die Prüfungen des Teils eingehen:

| Teil | Dateien | Prüfungen |
|---|---|---|
| `backend` | alles außer `frontend/`, `docs/` und `*.md` im Hauptverzeichnis | ruff, Migrationen, Proxy-/Rückweg-Prüfungen, pytest |
| `frontend` | `frontend/`, `scripts/test.sh` und Backend-Dateien, die der Frontend-Code beim Namen nennt (z. B. `backend/accounts/learning_keys.json`) | Typprüfung, Lint, Format, i18n, Vitest |
| `migration` | Vorlagen-Schlüssel (s. u.), Tests mit `@pytest.mark.migration`, `conftest.py`, `factories.py` und die von diesen Tests eingebundenen Module | Tests, die hin- und zurückmigrieren |

Ein Teil, dessen Inhalt schon grün war, läuft nicht noch einmal; sind alle Teile schon grün,
braucht der Lauf keinen Testplatz. Danach wird der Git-Tree wie immer in `tested-trees`
vermerkt (mit dem Zusatz `teilweise`), `deploy/deploy.sh` prüft unverändert nur ihn.
Ändert ein PR nur das Frontend oder die Hilfe, laufen also nur die Frontend-Prüfungen;
ändert er nur Doku, läuft nichts.

Werden zwei PRs nacheinander gemergt, hat main danach einen neuen Backend-Inhalt, und das
Backend läuft vollständig. Zwei Migrationen mit derselben Nummer in einer App fallen so
nicht durch. `makemigrations --check` läuft gleich nach ruff und meldet fehlende oder
widersprüchliche Migrationen nach Sekunden.

`TEST_ALLES=1 scripts/test.sh …` prüft alles, auch die Migrationstests. Vor einem Release
den Stand so testen (siehe [releases.md](releases.md)). Läufe mit eigenen
pytest-Argumenten und `BACKUP_TEST=1` laufen ebenfalls vollständig.

Fehlt der angegebene Commit im Klon, holt `scripts/test.sh` erst von allen Remotes
(`git fetch --all`). Ist er dann immer noch nicht da, bricht es mit Exit 2 ab. Jeder
Fehlschlag endet mit der Zeile `FEHLGESCHLAGEN (Exit …)`, nur ein vollständiger Lauf mit
`Alles grün: …`. Vorher im verwendeten Klon `git fetch origin` ausführen.

Das Skript überträgt den eingecheckten Stand (`git archive`), baut die Images auf dem
Server und startet alles neu. Datenbank und `.env` bleiben erhalten.

## Testplätze

Damit sich mehrere Testläufe auf einem Rechner nicht ausbremsen, auch aus verschiedenen
Projekten, verteilt `scripts/testplatz.sh` sie auf Testplätze:

```bash
testplatz [--kerne N] <befehl …>   # wartet auf einen freien Platz, dann läuft der Befehl
```

- Ohne Einstellung gibt es einen Platz mit allen Kernen. Mehr Plätze oder weniger Kerne
  stellt jeder Rechner lokal in `~/.config/testplatz` ein (nicht im Repo), zum Beispiel
  `PLAETZE=2` und `KERNE=4`, oder über `TESTPLATZ_PLAETZE` und `TESTPLATZ_KERNE`.
- Sperren liegen in `~/.testplaetze/platz-N.lock`. Wer keinen freien Platz findet, wartet. Bricht ein Lauf ab, gibt das System den Platz von selbst frei.
- Der Befehl ist an die Kerne seines Platzes gebunden (WSL: `taskset`; Windows:
  Prozessor-Affinität; die Plätze liegen nebeneinander ab Kern 0) und bekommt
  `TEST_KERNE` (Anzahl), `TESTPLATZ_CPUS` (für `docker run --cpuset-cpus`) und
  `TESTPLATZ` (Nummer). Docker-Container erben die Bindung nicht, deshalb setzen die
  Testskripte `--cpuset-cpus` selbst.
- Es läuft in WSL und in Git Bash unter Windows; unter Windows holt es den Platz über
  WSL (Distribution `Debian`, änderbar mit `TESTPLATZ_DISTRO`).
- Ältere Testskripte mit der exklusiven Sperre `~/.hubiplan-tests.lock` belegen alle
  Plätze, bis sie umgestellt sind. Startet man ein solches Skript selbst mit `testplatz`, bekommt es
  über `HUBIPLAN_TEST_LOCK` eine eigene Sperrdatei und belegt nur diesen einen Platz.

Installation (einmal und nach Änderungen an `scripts/testplatz.sh`):

```bash
install -m 755 scripts/testplatz.sh ~/.local/bin/testplatz   # in WSL
install -m 755 scripts/testplatz.sh ~/bin/testplatz          # in Git Bash unter Windows
```

`scripts/test.sh` von hubiplan holt sich den Platz selbst (über die Kopie im Repo),
ebenso `scripts/test.sh` in `hubiplan-website` und `hubiplan-android` (über das
installierte `testplatz`). Andere Projekte: Testbefehl mit `testplatz` starten und
`TEST_KERNE` als Anzahl der Worker nehmen.

### Was die Tests schnell hält

- **Testdatenbank als Vorlage:** `scripts/test.sh` migriert einmal und kopiert die
  Datenbank je Worker (`CREATE DATABASE … TEMPLATE`), statt in jedem Worker alle
  Migrationen laufen zu lassen (je ~40 s Rechenzeit). Die migrierte Datenbank liegt als
  `pg_dump` im konfigurierten Test-Cache (zehn neueste). Der Dateiname ist
  ein Schlüssel über Migrationen, die von ihnen eingebundenen Module, Modelle, `apps.py`,
  Einstellungen, Abhängigkeiten und das Datenbank-Image; ändert sich davon etwas, wird neu
  migriert. `TEST_DB_CACHE=0` schaltet die Vorlage ab, `TEST_DB_CACHE=<ordner>` legt sie
  woanders ab.
- **Schneller Passwort-Hasher in Tests** (`tests/conftest.py`): PBKDF2 kostet je Passwort
  ~0,2 s. Im Betrieb bleibt PBKDF2.
- **Migrationstests nur bei Bedarf:** Tests mit `@pytest.mark.migration` migrieren über
  den ganzen Baum hin und zurück und brauchen über ein Drittel der Rechenzeit. Sie laufen
  nur, wenn ihr Schlüssel (siehe „Nur geänderte Teile“) noch nicht grün war.
  `tests/test_migrations.py` prüft, dass jeder Test mit `MigrationExecutor` die Markierung trägt.
- **Langsame Tests zuerst:** Tests mit `@pytest.mark.langsam` (Migrationstest, Demodaten)
  sammelt pytest zuerst; mit `--maxschedchunk=2` verteilt xdist sie auf verschiedene Worker,
  statt dass einer am Ende allein läuft.
- **Tests mit `transaction=True`** leeren am Ende alle Tabellen. `tests/conftest.py` legt
  danach die Zeilen aus Datenmigrationen (z. B. die Plattform-Organisation) wieder an,
  damit nachfolgende Tests nicht von der Reihenfolge abhängen.
- **Frontend:** Vitest läuft mit `pool: 'vmThreads'` (jsdom einmal je Worker statt je
  Datei, etwa halbe Laufzeit). `window.location` lässt sich darin nicht ersetzen;
  Weiterleitungen laufen über `leaveTo.go` (`api/peering.ts`), Tests ersetzen diese.

## Nützliche Befehle auf dem Server

```bash
cd /opt/hubiplan
docker compose -f docker-compose.server.yml ps          # Status
docker compose -f docker-compose.server.yml logs -f web backend
docker compose -f docker-compose.server.yml exec backend python manage.py createsuperuser
```

## Demodaten

Pilotorganisationen mit erfundenen Mitgliedern (Adressen auf `.test`):
Dachverband „Bürger-Schützenverein Neuss-Grimlinghausen von 1855 e.V.“ mit dem Verein
„Hubertus-Schützenverein Neuss-Grimlinghausen von 1920“ und seinen 14 Zügen.

```bash
docker compose -f docker-compose.server.yml exec backend python manage.py seed_testdata
```

Ohne `--password` wird ein zufälliges Passwort für alle Testzugänge erzeugt und einmal
ausgegeben. Testzugänge: `plattform@hubiplan.test` (Plattform),
`vorstand@bsv-grimlinghausen.test` (Vorstand Dachverband),
`vorstand@hubertus-grimlinghausen.test` (Vorstand Verein),
`kasse@hubertus-grimlinghausen.test` (Kassierer, eingeschränkte Rechte).

Frühere Demo-Organisationen samt Zugängen, Mitgliedern, Fotos und Dateien entfernen
(erst mit `--dry-run` prüfen):

```bash
docker compose -f docker-compose.server.yml exec backend python manage.py seed_testdata --remove-legacy-demo --dry-run
docker compose -f docker-compose.server.yml exec backend python manage.py seed_testdata --remove-legacy-demo
```

### Zusätzlicher Demoverein mit Korps

„Schützenverein Musterstadt 1823 e.V.“ direkt unter der Plattform: sieben Korps, darunter
Züge (das Tambourkorps ohne Züge), alle schaltbaren Module und Zusatzfunktionen an, mit
erfundenen Daten für Mitglieder, Kasse, Beiträge, Termine, Würden, Wettbewerbe, Meldungen,
Rundschreiben-Entwurf und Webseite mit Chronik (`organizations/demo_korps.py`). Wiederholbar;
die Pilotorganisationen und alle anderen Daten bleiben unverändert.

```bash
docker compose -f docker-compose.server.yml exec backend python manage.py seed_demoverein
```

Testzugänge: `vorstand@`, `kasse@`, `schriftfuehrer@sv-musterstadt.test` (Vereinsrollen),
`major.jaeger@sv-musterstadt.test` (Major des Jägerkorps, über den Mitgliederbereich) und
`mitglied@sv-musterstadt.test` (einfaches Mitglied). Ohne `--password` wird ein zufälliges
Passwort erzeugt und einmal ausgegeben.

### Zweiter Demoverein: Musikkapelle

„Musikkapelle Musterdorf 2009 e.V.“ direkt unter der Plattform, ohne Untereinheiten, in Blau
und Gold: Musiker mit Instrumenten, Vorstand mit Dirigent auf der Webseite, Ehrenmitglieder,
verstorbene Mitglieder im Archiv, Termine, Stücke und eine Webseite mit Kopfbild, Galerie und
dem Menü „Aktuelles · Kapelle · Termine · Galerie · Kontakt“ (`organizations/demo_kapelle.py`).
Ist ein Designpaket mit dem Schlüssel `kapelle-furth` eingespielt, nimmt die Webseite es.
Wiederholbar wie oben.

```bash
docker compose -f docker-compose.server.yml exec backend python manage.py seed_demokapelle
```

Testzugänge: `vorstand@`, `kasse@`, `schriftfuehrer@mk-musterdorf.test`. Ohne `--password`
wird ein zufälliges Passwort erzeugt und einmal ausgegeben.

## Tests gegen PostgreSQL

Nur lokal, siehe „Ausrollen“: `scripts/test.sh` (mit `BACKUP_TEST=1` auch Backup
und Rücksicherung). Auf dem Server laufen keine Tests.

## Vereinswebseite (hubiplan-website)

Die Vereinsseite aus dem Repository `hubiplan-website` läuft auf dem Testserver als eigener
Container `website` im Docker-Netz `hubiplan_web`. Caddy leitet
`https://test.example.org/webseite/` dorthin weiter; läuft der Container nicht, antwortet
nur dieser Pfad mit einem Fehler.

In `/opt/hubiplan/.env`:

```bash
WEBSITE_PREVIEW_ONLY=true          # alle Webseiten nur in der Vorschau (erfundene Daten)
WEBSITE_PUBLIC_URL=https://test.example.org/webseite/
```

`seed_testdata` richtet die Webseite des Demovereins mit erfundenen Inhalten ein
(Domain `www.hubertus-grimlinghausen.test`, Wartungsmodus). Ansehen: in HUBIplan unter
Webseite › Einstellungen „Vorschau öffnen“.
