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

### Merge-Zug (Regel für alle Threads in hubiplan)

hubiplan-PRs werden **nacheinander** gegen den aktuellen main getestet und gleich danach gemergt.
So bewegt sich main während eines Laufs nicht, es gibt keine Nachtests, und der neue main ist ohne
eigenen Lauf ausrollbar.

```bash
scripts/zug.sh <PR-Nummer>   # vorprüfen, einreihen, auf main mischen, testen
scripts/zug.sh --status      # Warteschlange und worauf der Zug wartet
scripts/zug.sh --fertig      # warten, bis der grüne Stand in main ist
```

1. Der Zug prüft den PR vor (siehe „Vorprüfung“) und reiht ihn für den Zug-Platz ein.
2. Ist der PR dran, mischt der Zug ihn lokal auf den neuesten main und testet genau diesen Stand
   mit `scripts/test.sh` (Vorlauf der geänderten Testdateien zuerst). Warten weitere PRs, fahren
   bis zu drei zusammen (`ZUG_BUENDEL`); ein PR mit Migrationen fährt allein. Ist ein Bündel rot,
   fährt der erste PR allein weiter, die anderen danach.
3. **Grün:** Der Zug nennt die PRs in ihrer Reihenfolge. Der Thread, der den Lauf gestartet hat,
   mergt sie **sofort** auf GitHub, genau in dieser Reihenfolge und je mit „Create a merge commit“.
   Der Zug hält seinen Platz so lange (höchstens 30 Minuten, `ZUG_WARTEN`), damit niemand
   dazwischen mergt. Danach hat main genau den getesteten Tree; `deploy/deploy.sh` rollt ihn ohne
   neuen Lauf aus. Wer im Bündel mitfuhr, bekommt das Ergebnis gemeldet und ist fertig.
4. **Rot oder Mischkonflikt:** Der PR fliegt raus; beheben (bei Konflikt main einmischen) und neu
   einreihen. Die anderen fahren weiter.

In hubiplan mergt niemand am Zug vorbei. Ausnahme Notfall: dann `scripts/test.sh --main` vor dem
Ausrollen. Andere Repos (Webseite, Apps) haben kurze Läufe und testen wie bisher mit ihrem
`scripts/test.sh`.

Zum Entwickeln bleibt `scripts/test.sh <ref>` (Zweig-Lauf auf einem normalen Platz). Für Zweige,
die nicht über den Zug kommen, gilt weiter: `scripts/nachtest-noetig.sh <getesteter-commit> origin/main`
(Exit 0: direkt mergen; Exit 1: main einmischen und neu testen), danach `scripts/test.sh --main`.
Es läuft immer nur ein main-Lauf; wer währenddessen `--main` startet, wartet ohne Testplatz.

### Vorprüfung

`scripts/vorpruefung.sh [ref]` prüft in Sekunden bis etwa zwei Minuten, woran volle Läufe am
häufigsten scheitern: ruff, Typprüfung, Lint, Prettier, i18n, die Hilfe-Tests (erzeugte
`backend/mcpserver/hilfe.json`, Fettschrift-Namen) und die Vitest-Dateien, die der Stand gegenüber
main ändert. Sie belegt keinen Testplatz, nutzt höchstens zwei Kerne mit niedriger Priorität und ist
nie eine Freigabe. `scripts/test.sh` startet sie, während der Lauf auf seinen Platz wartet (rot → Lauf endet sofort); `scripts/zug.sh` prüft vor dem Einreihen
(`TEST_VORPRUEFUNG=0`: aus); ein grüner Tree wird vermerkt. Ohne Docker, z. B. in einer
Cloud-Sitzung vor dem Lauf auf dem Testrechner, läuft sie mit dem installierten node/npm
(`VORPRUEFUNG_OHNE_DOCKER=1`) und holt sich ruff in der festgeschriebenen Fassung.

### Läufe abbrechen

Jeder Lauf meldet oben seine **Lauf-ID** (`hubiplan-test-<Zeit>-<PID>`), und alle seine Container
und Netze tragen das Docker-Label `hubiplan.lauf=<ID>`.

```bash
scripts/test.sh --laeufe                 # laufende Läufe mit ID, Commit, Start, Platz
scripts/test.sh --abbrechen <Lauf-ID>    # nur diesen Lauf beenden und aufräumen
```

**Nie** über eine Mustersuche abbrechen (`pkill -f …`, `docker rm $(docker ps -q …)`): Das trifft
die Läufe anderer Threads. Ein Lauf, der noch auf einen Platz wartet, hat noch keine Container;
er steht in `testplatz --liste` mit seiner PID und lässt sich mit `kill <PID>` beenden.

### Messprotokoll

Jeder Lauf hängt eine Zeile an `laeufe.csv` (im selben Ordner wie die Datenbank-Vorlagen, sonst
neben `tested-trees`; `TEST_PROTOKOLL=<datei>` oder `0` für keines):
Lauf-ID, Commit, Platz, Kerne, Wartezeit, Rüsten, Frontend, Vorlauf, pytest, gesamt, Ergebnis
(grün, rot, abgebrochen, teil-grün), erster roter Test und Last. pytest gibt die 30 langsamsten
Tests aus (`TEST_DURATIONS`). Wackelige und langsame Tests werden nach diesem Protokoll angegangen.

### Wackelige Tests

`backend/tests/wackelig.txt` führt Tests, die bekanntermaßen ab und zu ohne Grund scheitern (eine
Zeile je Test, wie pytest ihn nennt). Sind in einem Lauf **nur** solche Tests rot (höchstens fünf),
wiederholt `scripts/test.sh` sie einmal allein; sind sie dann grün, gilt der Lauf als grün, und das
Messprotokoll vermerkt `gruen-wackelig`. Jeder andere rote Test bleibt rot. Die Liste soll
schrumpfen: Wer einen Eintrag repariert, streicht ihn.

### Reihenfolge eines Laufs

1. Gleiche Prüfung nur einmal: Prüft gerade ein anderer Lauf dasselbe Backend (gleicher
   Schlüssel, s. u.), wartet der Lauf ohne Testplatz auf dessen Ergebnis.
2. Warteschlange für den Testplatz (siehe „Testplätze“).
3. Frontend-Prüfungen im Hintergrund, Backend-Vorbereitung (Image, ruff, Migrationen,
   Proxy-/Rückweg-Prüfungen, Testdatenbank).
4. Vitest allein. Ein grünes Frontend wird sofort vermerkt.
5. **Vorlauf:** die Testdateien, die der Stand gegenüber main ändert (höchstens 30),
   ohne Migrationstests. Scheitert einer, endet der Lauf hier.
6. pytest vollständig; ein grünes Backend wird sofort vermerkt. Scheitert danach etwas,
   läuft beim nächsten Versuch nur noch der Rest.

### Nur geänderte Teile

`scripts/test.sh` merkt sich in `~/.local/state/hubiplan/tested-parts` zusätzlich, welche
Teile mit welchem Inhalt grün waren. Der Schlüssel ist ein Hash über die Dateien, die in
die Prüfungen des Teils eingehen:

| Teil | Dateien | Prüfungen |
|---|---|---|
| `backend` | alles außer `frontend/`, `docs/` und `*.md` im Hauptverzeichnis | ruff, Migrationen, Proxy-/Rückweg-Prüfungen, pytest |
| `frontend` | `frontend/`, `scripts/test.sh` und Backend-Dateien, die der Frontend-Code beim Namen nennt (z. B. `backend/accounts/learning_keys.json`) | Typprüfung, Lint, Format, i18n, Vitest |
| `migration` (je Testdatei) | die Datei, `conftest.py`, `factories.py`, die von ihr eingebundenen Module, Abhängigkeiten, Datenbank-Image und die Migrationen der Apps, deren Stände die Datei nennt (ohne genannten Stand: der Vorlagen-Schlüssel, s. u.) | Tests mit `@pytest.mark.migration` |

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
- Plätze verschiedener Größe: `PLATZ_KERNE="12 6"` (Kerne je Platz). `ZUG_PLATZ=1` behält
  Platz 1 dem Merge-Zug vor (`testplatz --zug`, nur `scripts/zug.sh`); alle anderen Läufe nehmen
  die übrigen Plätze und haben ihre eigene Warteschlange. Ohne `ZUG_PLATZ` nimmt der Zug einen
  beliebigen Platz wie jeder andere Lauf.
- Sperren liegen in `~/.testplaetze/platz-N.lock`. Wer keinen freien Platz findet, stellt
  sich in die Warteschlange `~/.testplaetze/warteschlange/`: Die Plätze werden in der
  Reihenfolge der Anfragen vergeben. Bricht ein Lauf ab, gibt das System den Platz und
  das Ticket von selbst frei. `testplatz --liste` zeigt belegte Plätze und Wartende.
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

Installation (einmal und nach Änderungen an `scripts/testplatz.sh`, immer an beiden Stellen,
weil WSL über den Windows-PATH auch die Git-Bash-Kopie findet):

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
  den ganzen Baum hin und zurück und brauchen über ein Drittel der Rechenzeit, der längste
  allein eine Viertelstunde. Jede Datei läuft nur, wenn ihr Schlüssel (siehe „Nur geänderte
  Teile“) noch nicht grün war, also vor allem, wenn sich die Migrationen ihrer eigenen Apps
  ändern. Eine neue Migration in einer anderen App lässt alte Migrationstests aus; die
  schon grünen Dateien gibt `scripts/test.sh` in `MIG_AUSLASSEN` an pytest weiter. Vor einem
  Release `TEST_ALLES=1`.
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
`https://test.example.org/vereinsseite/` dorthin weiter; läuft der Container nicht, antwortet
nur dieser Pfad mit einem Fehler. Nicht `/webseite/`: Diesen Pfad nutzt die Verwaltung
(Webseite › Gestaltung …), beim Neuladen käme sonst die Vereinswebseite (Fehler 400).
`scripts/pruefe-proxy.sh` prüft, dass kein Proxy-Pfad einen Bereich der Oberfläche verdeckt.

In `/opt/hubiplan/.env`:

```bash
WEBSITE_PREVIEW_ONLY=true          # alle Webseiten nur in der Vorschau (erfundene Daten)
WEBSITE_PUBLIC_URL=https://test.example.org/vereinsseite/
```

`seed_testdata` richtet die Webseite des Demovereins mit erfundenen Inhalten ein
(Domain `www.hubertus-grimlinghausen.test`, Wartungsmodus). Ansehen: in HUBIplan unter
Webseite › Einstellungen „Vorschau öffnen“.
