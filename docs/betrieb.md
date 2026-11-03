# Betrieb

Gilt für den Testserver (`docker-compose.server.yml`) und den Echtbetrieb. Ausrollen
siehe [testserver.md](testserver.md) und [echtbetrieb.md](echtbetrieb.md). Auf dem
Echtserver gehört zu jedem `docker compose`-Befehl zusätzlich `-f docker-compose.proxy.yml`.

## Dienste

| Dienst | Aufgabe |
| --- | --- |
| `web` | Caddy: HTTPS (Let's Encrypt), Oberfläche, Weiterleitung an das Backend, Sicherheits-Header |
| `backend` | Django mit gunicorn (3 Prozesse × 4 Threads), führt beim Start die Migrationen aus |
| `worker` | Celery: Import, Export und andere Hintergrund-Jobs |
| `beat` | Zeitplan für wiederkehrende Jobs (Löschfrist täglich) |
| `backup` | tägliches verschlüsseltes Backup mit Rücksicherungstest |
| `postgres`, `redis` | Datenbank und Warteschlange, von außen nicht erreichbar |

Die Anwendung arbeitet in der Datenbank mit der eingeschränkten Rolle `hubiplan_app`
(kein Superuser, kein BYPASSRLS). So greift der Zeilenschutz (Row-Level Security) auch,
falls in der Anwendung ein Filter fehlt.

Backend, Worker und Beat **melden sich direkt als `hubiplan_app` an** (Passwort
`APP_DB_PASSWORD`). Den Zugang des Datenbank-Superusers (`POSTGRES_PASSWORD`) nutzen nur
die Migrationen beim Start des Backends und das Backup; das Startskript entfernt ihn,
bevor gunicorn startet. Selbst Schadcode in der Anwendung kann die Rolle deshalb nicht
verlassen: kein `RESET ROLE` zum Superuser, keine Shell-Befehle über die Datenbank, kein
Abschalten von RLS. Nach einer Rücksicherung setzt der nächste Start Rechte und Passwort
der Rolle neu.

**Abschottung der Container** (`docker-compose.server.yml`):

- Backend, Worker und Beat laufen mit **schreibgeschütztem Dateisystem**: Schadcode kann
  den Programmcode nicht verändern. Schreibbar sind nur `/tmp` (Arbeitsspeicher) und die
  Daten-Volumes. Statische Dateien werden deshalb schon beim Bauen eingesammelt.
- Alle Container ohne Linux-Sonderrechte (`cap_drop: ALL`, Caddy nur mit dem Recht für
  Port 80/443) und ohne Rechteausweitung (`no-new-privileges`). Postgres braucht für
  den Start den Benutzerwechsel und behält seine Standardrechte.
- Drei Netze: `intern` (Postgres, Redis; ohne Weg ins Internet, für Caddy
  unerreichbar), `web` (Caddy ↔ Backend), `ausgang` (Mailversand, Backup-Zweitort).

**Zugriffslog des Backends:** Zeit, Methode, Pfad (ohne `?…`), Status, Größe und
Antwortzeit in Sekunden (letzte Spalte), ohne IP-Adresse. Langsamste Abrufe der letzten
drei Stunden:

```sh
docker compose logs --since 3h backend | grep -E '"(GET|POST) ' \
  | awk '{print $NF, $(NF-3)}' | sort -rn | head -25
```

**Vorwärmen:** Jeder neue gunicorn-Prozess ruft vor der ersten echten Anfrage
`/api/health/` und `/api/public/site/v1/resolve/` bei sich selbst auf
(`backend/gunicorn.conf.py`). Im Log steht dann je Prozess „Vorwärmen …: 200 OK“ bzw.
„404 Not Found“. Das lädt Anwendungs- und Resolvercode. Datenbankverbindungen sind
threadlokal; jeder gthread-Requestthread öffnet seine Verbindung erst bei seiner ersten
Anfrage. Die ungenutzte Hauptthread-Verbindung wird danach geschlossen. Daraus folgt
keine gemessene oder garantierte Verkürzung der ersten echten Anfrage.

English: Warmup loads application/resolver code. Django database connections are
thread-local: each gthread request thread connects on its first request. The unused
main-thread connection is closed afterwards; no measured first-request latency guarantee
is implied.

**Paginierte Mitgliederliste:** Die Liste übernimmt die konfigurierte JIT-Einstellung.
Eine historische lokale PostgreSQL-18-Messung mit 10.000 synthetischen Mitgliedern und
App-Rolle/RLS am P01-Stand `1af9ec0b` (Mess-Snapshot `afef8f1`) ergab 147,7/45,5 ms
ORM-Median mit/ohne JIT. Die spätere zentrale Namenssuche und Personensortierung ändert
den Plan erheblich. Beim erneuten lokalen Vergleich am integrierten Stand `3c1563f4`
ergaben ein Warmup und drei Durchläufe je Einstellung 675,7 ms [580,5–707,8] mit JIT und
624,5 ms [551,4–657,7] ohne JIT bei jeweils acht Abfragen und identischen Ergebnissen.
Die stark überlappenden Bereiche belegen für diesen neuen Plan keinen stabilen Vorteil.
Die zunächst vorgesehene besondere JIT-Abschaltung samt eigener Listentransaktion wurde
deshalb entfernt. Keine globale Datenbankänderung, kein RLS-Bypass und keine Produktions-
oder HTTP-Latenzgarantie. Ein späteres Tuning benötigt eine neue Messung des dann
tatsächlichen Plans mit repräsentativen Daten und kontrollierter Last.

English: The member list inherits the configured JIT setting. A historical local
10,000-member PostgreSQL-18/app-RLS measurement at P01 source `1af9ec0b` (snapshot
`afef8f1`) showed 147.7/45.5 ms ORM medians with/without JIT. Centralized name search
and person ordering subsequently changed the plan. A new comparison at integrated source
`3c1563f4`, one warmup and three runs per setting, showed 675.7 ms [580.5–707.8] with JIT
and 624.5 ms [551.4–657.7] without, eight queries each and identical results. These
overlapping ranges do not establish a stable benefit for the new plan. The proposed
special JIT setting and its list-only transaction were therefore removed. No global
database change, RLS bypass or production/HTTP latency guarantee is implied. Future
tuning requires measuring the then-current plan with representative data and controlled load.

## Geheimnisse

Alle Geheimnisse stehen nur in `/opt/hubiplan/.env` auf dem Server (Rechte 600), nie im
Repository. Beim ersten Ausrollen erzeugt `deploy/server-setup.sh` zufällige Werte für
`DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, `APP_DB_PASSWORD`, `REDIS_PASSWORD`, `BACKUP_PASSPHRASE`, `BACKUP_HMAC_KEY`
(Prüfsummen der Backups) und `MFA_ENCRYPTION_KEY` (verschlüsselt die 2FA-Geheimnisse in
der Datenbank). Fehlende Einträge ergänzt es bei jedem Ausrollen, vorhandene bleiben.

> **Wichtig:** `BACKUP_PASSPHRASE`, `BACKUP_HMAC_KEY` und `MFA_ENCRYPTION_KEY`
> zusätzlich sicher verwahren (z. B. KeePassXC), ebenso den privaten Backup-Schlüssel
> (siehe Backups). Ohne ihn bzw. die Passphrase lassen sich die Backups nicht
> entschlüsseln. Der `MFA_ENCRYPTION_KEY` liegt bewusst nicht im Backup:
> fehlt er nach einer Rücksicherung, müssen alle Benutzer ihre 2FA neu einrichten.
>
> Schlüsselwechsel für 2FA: In der `.env` `MFA_ENCRYPTION_KEYS=neuer,alter` setzen
> (hat Vorrang vor `MFA_ENCRYPTION_KEY`; Backend, Worker und Beat bekommen ihn über die
> gemeinsame Umgebung), `docker compose -f docker-compose.server.yml up -d`, dann
> `docker compose -f docker-compose.server.yml exec backend python manage.py
> mfa_schluessel_wechseln`. Danach `MFA_ENCRYPTION_KEY=neuer` setzen,
> `MFA_ENCRYPTION_KEYS` leeren und erneut `up -d`. Den alten Schlüssel erst löschen,
> wenn kein Backup mit Datenbankstand vor dem Wechsel mehr gebraucht wird.

## Verschlüsselung der Daten

Private Dateien (Mitgliederfotos, Dokumente, Belege, Rundschreiben-Anhänge, Importe,
Exporte, Bilder der Webseite) liegen verschlüsselt im Volume `private-data`
(`core/crypto.py`, `core/privatefiles.py`). Logos und Wappen (`media-data`) sind
öffentlich und bleiben unverschlüsselt.

Dazu kommen einzelne Felder in der Datenbank (`core/encfields.py`): Geburtsdatum,
E-Mail-Adresse, Telefon und Straße der Mitglieder, SEPA-Mandate (Kontoinhaber, IBAN, BIC), die IBAN der
Gegenseite in Kontoauszügen, die Werte der Zusatzfelder, die Inhalte des
Änderungsprotokolls und der Rückgängig-Daten sowie der Text von Mails im Postausgang
(Anhänge liegen als Dateien verschlüsselt). Empfänger und Betreff bleiben lesbar, damit
die Suche geht. In der Spalte steht `enc1:…`; leere Werte bleiben leer. Die Prüfsummen
des Änderungsprotokolls gelten für den Klartext, die Kette bleibt beim Verschlüsseln
gültig. Die Datenbank kann darin nicht suchen; die Suche nach E-Mail-Adressen und
Kontoinhabern läuft deshalb in HUBIplan selbst.

Auch die Kontaktkopien auf Rechnungen (Empfängeranschrift und E-Mail) und in
Rundschreiben-Empfängern (Anschrift, E-Mail und gespeicherte Platzhalterwerte) werden
verschlüsselt. Historische Versand- und Rechnungsstände bleiben dabei erhalten.
Es gilt der Schlüssel der ausstellenden bzw. versendenden Organisation, auch wenn
der Empfänger einem anderen Verein angehört. Die Namensfelder bleiben lesbar.

**Umfang und Grenzen:** Vor- und Nachnamen der Mitglieder (`Person`) bleiben im
Klartext. Das Geburtsdatum ist bereits verschlüsselt; Datumsvergleiche, Altersfilter
und die Sortierung danach laufen in Python. Bei den Kontaktdaten sind E-Mail,
Telefon und Straße verschlüsselt, Postleitzahl, Ort und Land bleiben lesbar.

Namenssuche und Personensortierung der Listen laufen bereits in HUBIplan selbst
(`members/personsearch.py`), nach Berechtigungs- und Fachfiltern und vor dem
Seitenschnitt. Unicode-Schreibvarianten und Groß-/Kleinschreibung werden vereinheitlicht;
`ß` entspricht `ss`. Für die feste Textreihenfolge gelten Grundbuchstaben zuerst,
danach Akzente und Schreibweise, zuletzt die Zeilen-ID. Umlaute stehen daher bei
ihrem Grundbuchstaben. Die Reihenfolge ist unabhängig von der Datenbank-Kollation.
Es gibt keinen Suchcache. Der strenge Identitätsabgleich für Import und Verbund bleibt
unverändert; Suchmarken und Namensverschlüsselung sind damit noch nicht eingeführt.

Eine beim Start installierte Compiler-Erweiterung (`core/encrypted_ordering.py`)
weist ORM-Sortierungen nach verschlüsselten Spalten zurück, auch über Beziehungen,
Annotationen und Standardsortierungen. Sie verwendet die interne Django-Compiler-API;
die Regressionstests dafür sind bei Django-Updates mitzuprüfen. Frei geschriebenes
SQL ist von dieser ORM-Sperre nicht erfasst.

Weitere Klartextkopien von Namen gibt es unter anderem
bei Rundschreiben-Empfängern (`circulars.Recipient`), Rechnungen (`billing.Invoice`),
Wettbewerbsstartern (`competitions.Starter`), Meldungen (`entries.EntryPerson`) und
Würden/Begleitungen (`honors.Reign`, `honors.Companion`). Auch Benutzerkonten
(`accounts`) enthalten Namen und E-Mail-Adressen.

Bei einem Diebstahl der Datenbank ohne Schlüssel schützt die Verschlüsselung die
verschlüsselten Inhalte. Die lesbaren Kopien und Beziehungen können Personen
weiterhin identifizierbar machen. Wer die laufende Anwendung samt Zugriff auf die
Schlüssel übernimmt, kann auch die verschlüsselten Inhalte lesen.

- **Schlüssel je Verein:** Jeder Verein (bzw. Dachverband, Plattform) hat einen eigenen
  Datenschlüssel (AES-256-GCM). Untereinheiten nutzen den ihres Vereins. Die
  Datenschlüssel liegen in der Tabelle `core_datakey`, verpackt mit dem Hauptschlüssel.
  Wird ein Verein gelöscht, fällt sein Datenschlüssel weg und seine Dateien sind nicht
  mehr lesbar (in Backups erst, wenn die Backups mit dem Schlüssel abgelaufen sind).
- **Hauptschlüssel:** Datei `DATA_KEY_FILE` (Standard `/opt/hubiplan-geheim/datenschluessel`,
  UID 1000, Gruppe 70, Rechte 0440), als Docker-Secret nur in Backend, Worker, Beat und
  Backup. Er steht nicht in der `.env`. `deploy/server-setup.sh` legt ihn beim ersten
  Ausrollen an und überschreibt ihn nie.
- **Kopie des Hauptschlüssels:** Das Backup legt bei jedem Lauf `datenschluessel_STAMP.age`
  neben die Backups, verschlüsselt mit dem öffentlichen Backup-Schlüssel. Sie geht mit
  restic an den zweiten Ort. Lesen kann sie nur, wer den privaten Backup-Schlüssel hat:
  `age -d -i hubiplan-backup.key datenschluessel_STAMP.age`. Ohne öffentlichen Backup-Schlüssel
  (alte Form) heißt die Kopie `datenschluessel_STAMP.enc` und ist mit der Backup-Passphrase
  verschlüsselt. Gelingt die Kopie nicht, gilt das Backup als **unvollständig**
  (Alarm-Mail, alte Backups bleiben). Die Kopie wird nie als „altes Backup“ gelöscht.
  Zusätzlich den Hauptschlüssel im Passwortmanager ablegen.
  > **Wichtig:** Ohne Hauptschlüssel sind die verschlüsselten Dateien auf dem Server und
  > in allen Backups verloren.
- **Austauschbare Quelle:** `DATA_KEY_PROVIDERS` (Standard `file`). Ein externer
  Schlüsseldienst kommt als weitere Quelle dazu; danach verpackt
  `manage.py datenschluessel_umverpacken` alle Datenschlüssel neu, die Daten bleiben
  unverändert (Konzept „Externer Schlüsselspeicher“). Ist die Quelle nicht erreichbar,
  antwortet die API mit 503.
- **Hauptschlüssel wechseln:** neue Zeile oben in die Schlüsseldatei (alte darunter
  lassen), `up -d`, `exec backend python manage.py datenschluessel_umverpacken`, danach die
  alte Zeile löschen und erneut `up -d`.
- **Bestand verschlüsseln:** Nach dem ersten Ausrollen mit Verschlüsselung (vorher ein
  frisches Backup) `exec backend python manage.py dateien_verschluesseln`. Wiederholbar;
  `--probe` zählt nur. Bis dahin liest HUBIplan alte Klartextdateien weiter.
  Für die Felder entsprechend `daten_verschluesseln` (auch `--probe`).
  Bei der Einführung der verschlüsselten Kontaktkopien zuerst Migrationen ausführen,
  dann den Feldbestand verschlüsseln und erneut mit `--probe` prüfen. Während des
  Bestandslaufs Backend und Hintergrundjobs als Schreiber anhalten; den Befehl in
  einem separaten Verwaltungscontainer ausführen. Ein Ergebnis von 0 bestätigt nur,
  dass keine umzuwandelnden Werte gefunden wurden; zusätzlich Lesbarkeit, Versand
  und PDF-Ausgabe prüfen. Bis zum Bestandslauf werden alte Klartextwerte weiter gelesen.
- **Rückweg:** `dateien_verschluesseln --entschluesseln` und
  `daten_verschluesseln --entschluesseln` legen alles wieder im Klartext ab.
  `deploy/zurueck.sh` macht das selbst, wenn die vorige Fassung die Verschlüsselung
  (bzw. dieselben Felder) noch nicht kennt. Nach dem nächsten Ausrollen wieder
  verschlüsseln.

## Backups

- **Wann:** täglich um `BACKUP_TIME` (Standard 03:15); beim allerersten Start sofort.
- **Was:** die Datenbank (`pg_dump`) und die Dateien (Logos, Mitgliederfotos,
  Import-/Exportdateien, Mails, Kassenbelege).
- **Wie:** gzip-komprimiert und mit dem **öffentlichen Schlüssel** des Betreibers
  verschlüsselt (`age`, Dateien `….age`). Der Server kann Backups damit erzeugen, aber
  nicht lesen: Wer den Server oder den Backup-Ort hackt, bekommt nur unlesbare Dateien.
  Den privaten Schlüssel hat nur der Betreiber. Ohne `BACKUP_PUBLIC_KEY` gilt noch die
  alte Form mit Passphrase aus der `.env` (`….enc`, `openssl enc -aes-256-cbc -pbkdf2`).
- **Wo:** `/opt/hubiplan-backups` auf dem Server, außerhalb der Docker-Volumes;
  Aufbewahrung `BACKUP_KEEP_DAYS` Tage (Standard 30).
- **Prüfsumme:** Zu jeder Datei gehört `….enc.hmac` (HMAC-SHA256 mit dem eigenen
  Schlüssel `BACKUP_HMAC_KEY` aus der `.env`; er steht dabei in keiner Befehlszeile).
  Eine veränderte oder untergeschobene
  Datei wird vor dem Entschlüsseln abgewiesen. Backups von vor der Einführung haben
  keine Prüfsumme und lassen sich mit `verify.sh --ohne-pruefsumme` weiter nutzen.
- **Rücksicherungstest:** Jedes Backup wird in eine leere Wegwerf-Datenbank
  eingespielt; mit öffentlichem Schlüssel direkt vor dem Verschlüsseln (der Klartext
  liegt dabei nur im Arbeitsspeicher des Backup-Containers), mit Passphrase direkt nach
  dem Verschlüsseln. In beiden Fällen läuft er, bevor alte Backups gelöscht werden und
  bevor die Kopie an den zweiten Ort geht. Das Ergebnis steht in `restore-test.log`, z. B.
  `Rücksicherung ok: db_…enc – 5 Organisationen, 208 Mitgliedschaften, Dateien: 40 gesichert, 38 Verweise, 0 fehlen`.
- **Dateiliste:** Datenbank und Dateien werden nacheinander gesichert. Zu jedem
  Dateiarchiv gehört deshalb `dateien_….sha256.age` (bzw. `.enc`): die Liste aller
  gesicherten Dateien mit SHA-256, im selben Moment wie das Archiv erstellt. Der
  Rücksicherungstest vergleicht sie mit den Dateiverweisen in der Datenbank (welche
  Spalten auf Dateien zeigen, steht in `deploy/backup/dateifelder.txt`; ein Test prüft
  die Liste gegen die Modelle). Fehlt eine Datei, steht sie als `WARNUNG` in
  `restore-test.log` und `backup.log`. Das Backup gilt dann als **unvollständig**: Es
  bleibt liegen, aber alte Backups werden nicht gelöscht und die Kopie an den zweiten Ort
  läuft ohne Löschen (`unvollständig, alte Backups bleiben` im Log).
- **Backup-Stand:** Der Backup-Container schreibt nach jedem Lauf `state`, `last_ok` und
  `text` in das Volume `backup-status`. Der Worker prüft stündlich: Bei Fehler, unvollständigem
  Backup oder wenn das letzte gelungene Backup älter als `BACKUP_MAX_AGE_HOURS` (Standard 26)
  ist, kommt höchstens einmal am Tag die Alarm-Mail „Backup prüfen“.
- **Zweiter Ort (vorbereitet):** `BACKUP_REMOTE=benutzer@host:/pfad/` in der `.env`
  setzen. Auf dem Server einen Ordner (Standard `/opt/hubiplan-backup-ssh`, sonst
  `BACKUP_SSH_DIR` in der `.env`) mit `id_ed25519` (privater Schlüssel nur für die
  Kopie) und `known_hosts` (Rechnerschlüssel des Ziels, z. B. `ssh-keyscan -t ed25519
  host`, Fingerabdruck vorher abgleichen) anlegen, beides `chown 70:70` und `chmod 600`
  (UID 70 = postgres im Backup-Container). Der Ordner wird schreibgeschützt nach
  `/run/backup-ssh` eingebunden und übersteht jedes Neuanlegen des Containers. Fehlt
  Schlüssel oder `known_hosts`, bricht das Backup mit `FEHLER` in `backup.log` ab,
  bevor alte Sicherungen aufgeräumt werden; eine gescheiterte Kopie steht ebenfalls als
  `FEHLER` im Log (das lokale Backup bleibt gültig). Ein geänderter Rechnerschlüssel des
  Ziels lässt die Kopie scheitern (kein „beim ersten Mal vertrauen“).

### Backup-Ziele

Die folgenden Ziele dienen als Vorlage; Zuständigkeiten und tatsächliche Sicherungsorte
werden je Installation in privaten Wiederherstellungsunterlagen festgelegt:

- **Höchstens 24 Stunden Datenverlust:** Das tägliche Backup reicht dafür. Bleibt es aus,
  meldet die Alarm-Mail „Backup prüfen“ das nach `BACKUP_MAX_AGE_HOURS` (26) Stunden.
- **Wiederanlauf innerhalb eines Tages** nach Totalausfall des Servers: neuer Server,
  HUBIplan ausrollen, letztes Backup einspielen (siehe Wiederherstellen).
- **Zweiter Ort:** eine getrennte Sicherung, zum Beispiel per restic
  (siehe [echtbetrieb.md](echtbetrieb.md)), mit unabhängig verwalteten Snapshots oder
  vergleichbarem Schutz gegen Löschen durch einen kompromittierten Anwendungsserver.
- **Schlüssel für den Notfall:** Für eine Wiederherstellung ohne Server und ohne lokalen Arbeitsrechner
  braucht es den privaten age-Schlüssel und gegebenenfalls das restic-Passwort sowie die
  Zugangsdaten des zweiten Sicherungsorts. Diese getrennt vom Server und zusätzlich offline
  sicher verwahren. Eine Vertretung (z. B. ein zweites Vorstandsmitglied) und den Zugriff
  im Notfall festlegen.
- **Unvollständige Backups** (fehlende Dateien) gelten nicht als gelungen: eigener Zustand,
  Alarm-Mail, alte vollständige Backups bleiben erhalten.
- Eine Wiederherstellungsübung auf einem leeren Rechner regelmäßig durchführen und das
  Ergebnis in den privaten Betriebsunterlagen dokumentieren.

### Backup-Schlüssel einrichten (einmalig, auf einem lokalen Arbeitsrechner)

In WSL (`sudo apt install age`) oder mit Docker:

```bash
age-keygen -o hubiplan-backup.key          # privater Schlüssel, NICHT auf den Server
# Ausgabe „Public key: age1…“ ist der öffentliche Schlüssel
```

`hubiplan-backup.key` in den Passwortmanager und ausgedruckt an einen sicheren Ort
(Vertretung regeln). Geht er verloren, sind alle damit verschlüsselten Backups verloren.
Den öffentlichen Schlüssel beim nächsten Ausrollen mitgeben (je Server ein eigenes
Schlüsselpaar):

```bash
BACKUP_PUBLIC_KEY=age1… deploy/deploy.sh
```

Ab dem nächsten Backup entstehen `….age`-Dateien. Ältere `….enc`-Backups bleiben mit der
Passphrase lesbar und laufen nach `BACKUP_KEEP_DAYS` Tagen aus.

Protokolle prüfen:

```bash
tail /opt/hubiplan-backups/backup.log /opt/hubiplan-backups/restore-test.log
```

### Wiederherstellen (Notfall)

```bash
cd /opt/hubiplan
set -a; . ./.env; set +a
DATEI=/opt/hubiplan-backups/db_JJJJ-MM-TT_HHMM.sql.gz.enc

# Erst die Prüfsumme prüfen (bricht bei veränderter Datei ab)
docker compose -f docker-compose.server.yml run --rm --no-deps --entrypoint verify.sh \
    backup "/backups/$(basename "$DATEI")"
docker compose -f docker-compose.server.yml stop backend worker beat
docker compose -f docker-compose.server.yml exec -T postgres \
    psql -U hubiplan -d postgres -c "DROP DATABASE hubiplan" -c "CREATE DATABASE hubiplan"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE -in "$DATEI" \
    | gunzip \
    | docker compose -f docker-compose.server.yml exec -T postgres psql -U hubiplan -d hubiplan
docker compose -f docker-compose.server.yml up -d   # vergibt die Rechte für hubiplan_app neu
```

Dateien entsprechend aus `files_….tar.gz.enc` in die Volumes `media-data` und
`private-data` zurückspielen. Danach im Zielordner (der `media/` und `private/` enthält)
mit der entschlüsselten Dateiliste prüfen, ob alles vollständig und unverändert ist:

```bash
sha256sum -c dateien_JJJJ-MM-TT_HHMM.sha256
```

**Backups mit öffentlichem Schlüssel (`….age`)** werden auf einem lokalen Arbeitsrechner entschlüsselt; der
private Schlüssel kommt nie auf den Server. Prüfsumme wie oben prüfen, Dienste stoppen
und Datenbank leeren, dann in WSL:

```bash
scp deploy@server.example.org:/opt/hubiplan-backups/db_JJJJ-MM-TT_HHMM.sql.gz.age .
age -d -i hubiplan-backup.key db_JJJJ-MM-TT_HHMM.sql.gz.age | gunzip \
    | ssh deploy@server.example.org "cd /opt/hubiplan && sudo docker compose -f docker-compose.server.yml exec -T postgres psql -U hubiplan -d hubiplan"
```

Danach `docker compose … up -d` wie oben.

**Löschliste:** Jede erledigte Löschung (Löschfrist, Löschen auf Verlangen, Verbund-Widerruf)
steht zusätzlich im Volume `loeschliste` (nur Kennungen und Zeitpunkte, keine Namen). Beim Start
des Backends und täglich wird sie erneut angewendet; so sind gelöschte Daten auch nach dem
Einspielen eines älteren Backups wieder weg (Alarm-Mail, wenn das passiert). Das Volume beim
Wiederherstellen **nicht** zurücksetzen. Auf einem neuen Server vor dem ersten Start die
neueste `loeschliste.jsonl` aus dem Backup-Ordner hineinkopieren (das Backup legt sie täglich
dorthin und kopiert sie an den zweiten Ort). Von Hand: `python manage.py loeschliste_anwenden`.

**Kettenköpfe:** Das Backup hängt täglich je Organisation Nummer und Prüfsumme des letzten
geprüften Eintrags im Änderungsprotokoll an `kettenkoepfe.log` im Backup-Ordner an (keine
Inhalte). Die Datei geht mit an den zweiten Sicherungsort; ältere Stände
bleiben in den Schnappschüssen. Abgleich mit der Datenbank:
`python manage.py kettenkoepfe_pruefen /pfad/kettenkoepfe.log`. Das macht Löschen oder
Neuberechnen der Kette sichtbar, solange die getrennte Kopie unberührt ist; gegen jemanden mit
vollem Zugriff auf Server und zweiten Sicherungsort schützt es nicht.

**Alte Startpasswörter:** `python manage.py startpasswoerter` zeigt nur die Anzahl der Konten,
die noch ein Startpasswort haben; mit `--umstellen` wird es unbrauchbar und die Person bekommt
einen Link zum Festlegen des Passworts.

## E-Mail

Jede Mail landet im **Postausgang** der Datenbank:

- Vereine und Dachverbände sehen ihre Mails unter Einstellungen → Postausgang.
- Plattform-Admins sehen alle Mails unter Plattform → Postfach (Test-Postfach).

Kontomails (Passwort geändert, Bestätigungslink für eine neue Anmelde-E-Mail) gehören
keiner Organisation und stehen nur im Plattform-Postfach. Solange SMTP fehlt, findet man
dort auch den Bestätigungslink, wenn jemand seine Anmelde-E-Mail ändert.

Rechnungen aus Beitragsläufen gehen mit PDF-Anhang an die Mitglieder bzw. an den
Kassierer der Abteilung (Abteilungsrolle mit dem Recht „Sammelrechnungen der Abteilung
sehen“). Ohne SMTP stehen sie im Postausgang des Vereins (Art „rechnung“).
Verbandsrechnungen des Dachverbands gehen an die Kontaktadresse des Vereins,
Mahnungen tragen die Art „mahnung“.
Vor jedem Lastschrifteinzug gehen Vorabankündigungen an die Zahler (Art
„vorabankuendigung“); wer ein Mandat im Mitgliederbereich erteilt, bekommt eine Bestätigung
(Art „mandat“). Die Lastschriftdatei (SEPA-XML, pain.008.001.08) lädt der Kassierer
herunter und reicht sie selbst im Online-Banking ein; die Software spricht nicht mit der Bank.

Solange kein SMTP-Zugang hinterlegt ist, wird nichts zugestellt. Für echten Versand in
der `.env` setzen und neu starten (die Mails bleiben zusätzlich im Postausgang):

```text
EMAIL_HOST=smtp.example.org
EMAIL_PORT=587
EMAIL_HOST_USER=…
EMAIL_HOST_PASSWORD=…
DEFAULT_FROM_EMAIL=hubiplan <noreply@example.org>
```

`DJANGO_EMAIL_BACKEND` nicht setzen, sonst fällt der Postausgang weg.

**Aufbewahrung:** Bei zugestellten Mails leert ein täglicher Job nach
`OUTBOX_RETENTION_DAYS` Tagen (Standard 30) Text und Anhänge. Empfänger, Betreff, Art und
Datum bleiben als Nachweis. Nicht zugestellte (und nur gespeicherte) Mails bleiben länger
vollständig, damit man sie erneut senden kann, aber nicht unbegrenzt: nach
`OUTBOX_FAILED_RETENTION_DAYS` Tagen (Standard 90, Fachfrage FQ14) werden auch sie geleert.

## Grenzen der Container

Backend und Worker haben feste Grenzen für Arbeitsspeicher und `/tmp`, damit ein großer
Upload oder Import nicht den ganzen Server lahmlegt. Anpassbar in der `.env`:
`BACKEND_MEM_LIMIT` (Standard `1536m`), `BACKEND_TMP_SIZE` (Standard `768m`),
`WORKER_MEM_LIMIT` (Standard `2g`). Der Worker läuft mit zwei parallelen Aufgaben. Caddy
nimmt höchstens 520 MB je Anfrage an.

Seit dem Audit vom 02.11. (O-P01) haben alle Dienste Obergrenzen, damit HUBIplan andere
Dienste auf einem geteilten Server (Hestia, Mail, Nextcloud) nicht verdrängt. Es sind
Höchstwerte, keine Reservierungen; was frei bleibt, nutzen die anderen.

| Dienst | Speicher | CPU | Anpassbar in der `.env` |
|---|---|---|---|
| Backend | 1536 MB | 2 | `BACKEND_MEM_LIMIT`, `BACKEND_CPUS` |
| Worker | 2 GB | 2 | `WORKER_MEM_LIMIT`, `WORKER_CPUS` |
| Beat | 256 MB | 0,5 | – |
| PostgreSQL | 2 GB | 2 | `POSTGRES_MEM_LIMIT`, `POSTGRES_CPUS` |
| Redis | 384 MB (Daten höchstens 256 MB) | 1 | `REDIS_MAXMEMORY` |
| Backup | 3 GB, davon `/tmp` höchstens 2 GB | 1 | `BACKUP_MEM_LIMIT`, `BACKUP_TMP_SIZE`, `BACKUP_CPUS` |
| Caddy | 256 MB | 1 | – |

Redis verwirft bei voller Grenze nichts (`noeviction`): Neue Einträge schlagen mit einem
Fehler fehl, wartende Aufträge bleiben erhalten. Das Backup legt den Dump für den
Rücksicherungstest in `/tmp` im Arbeitsspeicher ab; wächst die Datenbank über etwa 1 GB,
`BACKUP_TMP_SIZE` und `BACKUP_MEM_LIMIT` erhöhen. Wird ein Dienst an seiner Grenze
beendet, startet Docker ihn neu (`restart: unless-stopped`); die anderen laufen weiter.

## Einladungen statt Startpasswort

Neue Konten (Rollen, Plattform-Vorstand) bekommen kein Startpasswort mehr, sondern eine
Einladung per Mail mit einem Link zum Festlegen des Passworts, 7 Tage gültig („Passwort
vergessen“ bleibt bei 3 Tagen). Alte Startpasswörter gelten wie bisher höchstens 7 Tage und
müssen bei der ersten Anmeldung ersetzt werden; ein stündlicher Job macht abgelaufene
unbrauchbar und meldet App-Geräte und Verbund-Anmeldungen des Kontos ab.

## Pflicht-2FA

Wer Rollen verwaltet, vollständige Exporte erstellt, in der Kasse bucht oder die Plattform
verwaltet, braucht die Zwei-Faktor-Anmeldung. Beim ersten Bedarf beginnen 14 Tage Übergang
(Hinweis oben auf jeder Seite); danach ruhen genau diese Rechte, bis 2FA eingerichtet ist
(für Plattform-Zugänge alle Plattformrechte). Handy verloren: mit einem
Wiederherstellungscode anmelden, oder eine zweite Person mit Rollenverwaltung und eigener
2FA setzt unter Rollen „2FA zurücksetzen“ (Mail an die Person, Alarm-Mail, Geräte werden
abgemeldet).

## Virenprüfung

Ist in der `.env` `CLAMD_SOCKET_DIR` gesetzt (Ordner mit dem Socket des clamd auf dem
Rechner, z. B. `/run/clamav`; Dateiname mit `CLAMD_SOCKET_NAME`, Standard `clamd.ctl`),
hängt `docker-compose.clamav.yml` den Ordner schreibgeschützt in Backend und Worker ein. Jede
hochgeladene Datei läuft dann während des Hochladens durch clamd:

- Fund: Upload abgelehnt, Alarm-Mail „Schadsoftware beim Hochladen abgelehnt“.
- clamd nicht erreichbar: Upload abgelehnt (Meldung „später noch einmal“), Alarm-Mail
  höchstens einmal je Stunde. Nach einem Neustart oder Update des clamd ggf. `backend` und
  `worker` neu starten, falls der Socket-Ordner neu angelegt wurde.
- Dateien über `CLAMD_MAX_BYTES` (Standard knapp 25 MB, die Grenze `StreamMaxLength` des
  clamd) bleiben ungeprüft und stehen im Log. Die Einstellungen des clamd (HestiaCP) bleiben
  unverändert.

Vor der Weitergabe prüft HUBIplan noch einmal mit den dann aktuellen Signaturen
(Fachfrage FQ16, Audit 02.11.): Anhänge eines Rundschreibens beim Versand und Dateien aus
öffentlichen Ordnern beim Abruf über den Link. Ein „sauber“ gilt dabei 6 Stunden. Ein Fund
stoppt den Versand bzw. den Abruf und schickt eine Alarm-Mail. Mit Virenprüfung gilt
`VIRUS_SCAN_REQUIRED=1` (Standard in `docker-compose.clamav.yml`): Dateien über
`CLAMD_MAX_BYTES` werden dann nicht weitergegeben, und fällt der Socket weg, auch nichts
anderes. Mit `VIRUS_SCAN_REQUIRED=0` in der `.env` geht Ungeprüftes wie früher durch
und steht nur im Log.

Ohne `CLAMD_SOCKET_DIR` (Testserver, Entwicklung) gibt es keine Prüfung.

## Alarm-Mails und Notfall

HUBIplan schickt sofort eine Mail „[HUBIplan-Sicherheit] …“ bei:

- einem Export ab `ALERT_EXPORT_ROWS` Zeilen (Standard 200) und jedem vollständigen
  Datenexport einer Einheit,
- einem neuen Zugang zur Plattform-Organisation,
- einem neu angelegten Superuser,
- im Verbund: Schlüsselwechsel (eigener und der Gegenstellen), Umzug einer Gegenstelle,
  gehäuft ungültige Unterschriften, eine Gegenstelle mit unerwartetem Schlüssel,
- in der App: ab 3 fehlgeschlagenen Freischaltungen der Verwaltung in einer Stunde.
- Backup fehlgeschlagen, unvollständig oder zu alt (siehe Backups; einmal am Tag).

Empfänger: `SECURITY_ALERT_EMAIL` in der `.env` (Komma-Liste), sonst alle Superuser.

**Wenn eine Meldung nicht erwartet war:**

1. Betroffenen Zugang sperren (Benutzer deaktivieren), Sitzungen enden damit.
2. Protokoll der Einheit prüfen: Wer hat was exportiert oder geändert?
3. Bei Verdacht auf einen Einbruch in den Server: Server vom Netz nehmen
   (`docker compose … down`), alle Schlüssel in der `.env` erneuern, Passwörter aller
   Plattform-Zugänge zurücksetzen.
4. Datenpanne melden: binnen 72 Stunden an die Datenschutzaufsicht (NRW: LDI NRW), bei
   hohem Risiko auch die betroffenen Vereine/Mitglieder informieren.

### Instanz vermutlich gehackt: Verbund und App

Wer auf dem Server war, kann die Schlüssel im privaten Speicher kopiert haben. Nach dem
Säubern des Servers (oben, Schritt 3) und vor dem Wiederanschalten:

1. **Verbund-Schlüssel im Notfall wechseln:**
   `docker compose exec backend python manage.py verbund_schluessel_wechseln --notfall`
   (oder Plattform › Einstellungen › Verbund › Notfallwechsel). Der Befehl zeigt den neuen
   Fingerabdruck und welche Partner die Ankündigung bekommen haben.
2. **Partner informieren**, am besten telefonisch: neuen Fingerabdruck vorlesen. Bei
   ihnen bestätigt die Plattformverwaltung den neuen Schlüssel (Plattform › Verbund);
   alle betroffenen Einheiten bekommen eine Mitteilung. Bis dahin ruht der Austausch.
3. **App-Geräte abmelden und Push-Schlüssel erneuern:**
   `docker compose exec backend python manage.py geraete_abmelden --push-schluessel`,
   danach Backend und Worker neu starten. Alle Mitglieder verbinden die App neu (QR-Code),
   die Verwaltung in der App ist damit für alle gesperrt.
4. **Vorstandszugänge:** Passwörter der Plattform- und Vorstandskonten zurücksetzen lassen;
   das meldet auch die Geräte dieser Konten ab.
5. Wer sich über eine andere Instanz anmeldet, braucht danach keine neue Verknüpfung; die
   Anmeldebestätigungen gelten mit dem neuen Schlüssel, sobald der Partner ihn bestätigt hat.

**Django-Admin** (`/admin/`) ist im Server-Betrieb aus. Bei Bedarf in der `.env`
`DJANGO_ADMIN_ENABLED=true` setzen und neu ausrollen, danach wieder entfernen.

Mails gibt es für:

- „Passwort vergessen“ (Link 3 Tage gültig) und Einladungen für neue Konten (Link zum
  Festlegen des Passworts, 7 Tage gültig),
- Zugänge für Mitglieder: Anmeldelink (7 Tage gültig, nur einmal nutzbar). Konten mit
  Vorstandsrollen oder 2FA bekommen statt dessen einen Link zum Festlegen des Passworts.

## Löschfrist

Der Job `members.tasks.purge_expired_members` läuft täglich. Nach Ablauf der in der
Plattform eingestellten Löschfrist bleiben von ehemaligen Mitgliedern nur Name, Vorname,
Geburtsjahr und die Mitgliedszeiträume; die Verbandsnummer wird gelöscht, sobald die Person
nirgends mehr Mitglied ist. Verlangt ein ehemaliges Mitglied die Löschung vorher, gibt es in
der Akte unter „Abläufe“ den Knopf „Daten auf Verlangen löschen“ (gleiches Ergebnis).
Rechnungen und Buchungen bleiben wegen der Aufbewahrungspflicht. Jede Löschung steht auf der
Löschliste (siehe Wiederherstellen). Eine verkürzte Löschfrist gilt erst nach 30 Tagen.
Alle Datenarten mit Rechtsgrundlage und Frist: [aufbewahrung.md](aufbewahrung.md).

**Auskunft (Art. 15 DSGVO):** In der Akte unter „Abläufe“ › „Auskunft für dieses Mitglied
(ZIP)“ (Recht „Vollständigen Datenexport erstellen“): Akte, Zusatzfelder, Rechnungen mit PDF,
Mandate, Zuwendungen, versandte Mails, Zugang und Geräte der App, Termin-Rückmeldungen,
Verbund-Meldungen und das Protokoll, ohne Daten anderer Personen.

## Updates

- Dependabot meldet wöchentlich Updates; Django bleibt auf der LTS-Version.
- Kritische Sicherheitslücken innerhalb weniger Tage einspielen, sonst monatlich.
- Vor dem Ausrollen lokal testen: `BACKUP_TEST=1 scripts/test.sh` (in WSL).
  Tests laufen nie auf dem Server; höchstens zwei Testläufe
  gleichzeitig, jeder höchstens 8 Kerne (`scripts/testplatz.sh`).
- Wer HUBIplan selbst betreibt, rollt am besten Releases aus (`deploy/deploy.sh v2026.11.0`
  oder mit Rückschritt-Prüfung `deploy/release-ausrollen.sh <ziel> v2026.11.0`)
  und liest vorher in [CHANGELOG.md](../CHANGELOG.md) den Abschnitt „Für Betreiber“.
  Versionen, Changelog und Rollout-Protokoll: [releases.md](releases.md).
- Einmal am Tag fragt HUBIplan den Releases-Feed auf GitHub ab
  (`HUBIPLAN_UPDATE_URL`, Standard: dieses Repository) und zeigt Plattformverwaltern einen Hinweis,
  wenn ein neueres Release als das laufende erschienen ist. Gesendet wird nichts; GitHub sieht
  nur die IP-Adresse des Servers (steht in der erzeugten Datenschutzerklärung).
  Abschalten mit `HUBIPLAN_UPDATE_CHECK=0` in der `.env`.

## Selbstupdate

Für Vereine, die HUBIplan selbst betreiben (Konzept `konzepte/selbstupdate.md`; nicht auf dem
Echtserver des Pilotvereins). Standardmäßig aus; einschalten mit `HUBIPLAN_SELBSTUPDATE=1` in
der `.env` und einmal ausrollen. Nötig sind systemd, `git` und `ssh-keygen` auf dem Server.

- HUBIplan darf nur einen **Auftrag** ablegen (Datei `auftrag` in `AKTUALISIERUNG_DIR`,
  Standard `/opt/hubiplan-aktualisierung`, im Backend als `/aktualisierung` eingebunden durch
  `docker-compose.selbstupdate.yml`). Den Auftrag legt nur ein Plattformverwalter mit
  Zwei-Faktor-Anmeldung und Passwort an, und nur für das Release, das die tägliche Prüfung
  gefunden hat (Seite Plattform › Version). Dabei geht eine Alarm-Mail an den Betreiber
  (`SECURITY_ALERT_EMAIL`, sonst die Superuser), und der Auftrag steht im Änderungsprotokoll
  der Plattform. Solange er läuft, fragt die Seite alle 10 Sekunden nach dem Ergebnis.
- Der **Aktualisierer** (`deploy/aktualisierer/aktualisierer.sh`, systemd-Timer
  `hubiplan-aktualisierer@hubiplan.timer`, jede Minute) läuft als root außerhalb der Container.
  Er holt den Tag aus `HUBIPLAN_UPDATE_REPO` in einen eigenen Spiegel (`/opt/hubiplan-quelle.git`)
  und rollt nur aus, wenn
  - der Tag mit einem Schlüssel aus `deploy/release-schluessel` der **laufenden** Fassung
    signiert ist,
  - er den laufenden Stand enthält (kein Rückschritt),
  - genug Platz zum Bauen da ist und keine Sperre (`/opt/hubiplan.sperre`) besteht.

  Dann sichert er die Datenbank über den Backup-Dienst und rollt aus wie `deploy.sh`
  (`server-setup.sh` mit automatischem Rückweg). Meldet die Sicherung „unvollständig“ (Dateien
  oder Schlüsselkopie fehlen), rollt er nicht aus. Ergebnis in `ergebnis` (in HUBIplan
  sichtbar), Ausgaben in `ausrollen.log` und `sicherung.log` im Ordner
  `/opt/hubiplan-aktualisierung.root` (nur root), eine Zeile im Rollout-Protokoll. Im
  Auftragsordner, der dem Backend gehört, schreibt der Aktualisierer keine Datei direkt; er
  legt das Ergebnis nur per Umbenennen hinein. Der root-Ordner muss auf demselben
  Dateisystem liegen wie der Auftragsordner.
- Ausschalten: `HUBIPLAN_SELBSTUPDATE=0` und einmal ausrollen; `server-setup.sh` schaltet den
  Timer dann ab.

## Ausrollen mit Rückweg

`deploy/deploy.sh` entpackt die neue Fassung nach `/opt/hubiplan.neu` (mit der
vorhandenen `.env`) und baut dort die Images, während die laufende Fassung weiterläuft.
Scheitert das Bauen, bleibt der Server unverändert. Danach tauscht `server-setup.sh` die
Ordner (`/opt/hubiplan` → `/opt/hubiplan.vorher`) und startet.

Es läuft immer nur ein Ausrollen je Server: `deploy.sh` legt zu Beginn die Sperre
`/opt/hubiplan.sperre` an (mit Fassung, Zeit und Rechner in `lauf`) und entfernt sie am Ende,
auch nach einem Fehler. Ein zweiter Lauf bricht ab und zeigt, wer gerade ausrollt. Bleibt die
Sperre nach einem harten Abbruch (Rechner aus, Verbindung weg) liegen, erst prüfen, dass kein
Lauf mehr arbeitet, dann `rm -r /opt/hubiplan.sperre` (Produktionsserver mit `sudo`).

Vor dem Tausch laufen die Migrationen als eigener Schritt (Ausgabe mit `-v 2`, höchstens
`MIGRATE_TIMEOUT` Sekunden, Standard 3600, änderbar in der `.env`). Dafür halten Backend,
Worker, Beat und Backup der bisherigen Fassung an, damit keine laufende Abfrage eine
Tabellensperre hält (am 31.10.2026 hing so `ALTER TABLE` auf dem Echtserver); Datenbank und
Redis laufen weiter. Stehen keine Migrationen an (`migrate --check`), entfällt das Anhalten. Hinter nginx hält auch Caddy an, und nginx zeigt solange die Seite
„HUBIplan wird gerade aktualisiert“, die sich alle 5 Sekunden neu lädt
(`deploy/hestia/app-8110.stpl`). Mit eigenem HTTPS wartet Caddy bis zu 30 Sekunden auf das
Backend und zeigt danach dieselbe Seite. Die Oberfläche wiederholt Anfragen bei 502/503/504
von selbst. Schlagen die Migrationen fehl, startet die bisherige Fassung wieder. Wird ein Dienst nicht
„healthy“, geht es automatisch zur vorigen Fassung zurück (Ordner und Images
`…:vorher`); die fehlerhafte bleibt zur Ansicht in `/opt/hubiplan.fehler`.

Läuft die neue Fassung, ist aber fachlich fehlerhaft, von Hand zurück:

```bash
ssh root@<testserver> "cd /opt/hubiplan && sh deploy/zurueck.sh"
ssh deploy@server.example.org "cd /opt/hubiplan && sudo sh deploy/zurueck.sh"
```

Ein zweiter Aufruf geht wieder vor. Welche Fassung läuft, steht in `/opt/hubiplan/.fassung`.
Datenbank-Migrationen der neueren Fassung bleiben dabei angewendet; Migrationen deshalb
so schreiben, dass die vorige Fassung damit weiterläuft (Spalten erst eine Fassung später
entfernen).


## Verifikation der Dateiarchive und lokale technische Satzprüfung

Die Sicherung prüft die tatsächlichen gzip/tar-Dateibytes streamingweise vor der
Verschlüsselung gegen die SHA-256-Dateiliste. Veränderte Inhalte, fehlende/zusätzliche
Dateien, Duplikate, unsichere Pfade, Links sowie defekte gzip-Trailer brechen die
Pipeline ab. Es wird kein vollständiges Klartext-Dateiarchiv im Server-tmpfs abgelegt.
Die Passphrase-Rücksicherung prüft zusätzlich das entschlüsselte signierte Archiv.
Der vorhandene SQL-Test spielt den Dump weiterhin in eine leere lokale PostgreSQL-Instanz.
DB-Verweise werden gegen die so geprüfte Dateiliste verglichen; fehlende Verweise
lösen weiterhin den Unvollständigkeitsmerker aus und verhindern die Altersbereinigung.

Bei age kann der Server nur die Daten **vor** Verschlüsselung prüfen. Den privaten
age-Schlüssel nicht auf den Server kopieren. Auf einem isolierten lokalen Rechner mit
Testplatz, PostgreSQL 18, age, OpenSSL und den Backup-Werkzeugen lässt sich ein kopierter
Sicherungssatz vollständig prüfen:

```sh
BACKUP_HMAC_KEY="$(cat /geschuetzt/hmac-key)" \
  restore-test.sh --age /sicherung/db_ZEIT.sql.gz.age /geschuetzt/restore-identity
```

`verify.sh` unterstützt die vorhandene HMAC-Konfiguration; vor Aufruf den Schlüssel
über die dokumentierte geschützte Umgebung bereitstellen. Kein Geheimnis auf die
Befehlszeile schreiben. Die Beispiele zeigen nur Musterpfade. Der lokale Restore
prüft HMAC, age-Entschlüsselung, tatsächliche Archiv-Prüfsummen und SQL-Restore.
Die zum Sicherungszeitpunkt gehörende verschlüsselte Hauptschlüsselkopie muss gegen
den signierten SHA-256-Fingerabdruck dieses Quellschlüsselrings passen. Jede
Schlüsselzeile muss 32 Byte ergeben; Kommentare und mehrere alte Rotationsschlüssel
werden wie in der Anwendung unterstützt. Alte Sätze ohne Fingerabdruck verlangen eine unabhängige manuelle
Schlüsselprüfung; der strenge neue Test akzeptiert sie nicht als vollständig geprüft.
Ein Restore ohne passende Dateiarchive ist ebenfalls kein vollständiger Satz.
Das belegt Wiederherstellbarkeit der geprüften Kopie, keine externe Kopier-/Transport-
oder zukünftige Hardwaregarantie. Temporäre Klartexte nur auf einem geschützten
lokalen Arbeitsdatenträger ablegen; der Test entfernt sie beim Ende.

English: archive contents are SHA-256 verified as a bounded stream before encryption.
A separate local `--age` restore with an independently supplied private identity checks
HMACs, decryption, actual archive bytes, database restoration and the recovered data-key
fingerprint. The private identity must never be installed on the production server.
Legacy key copies without authenticated source fingerprints need independent verification.

Der entsprechende strenge lokale Test für Passphrase-Sätze heißt
`restore-test.sh --passphrase /sicherung/db_ZEIT.sql.gz.enc`; er benötigt zusätzlich
`BACKUP_PASSPHRASE` aus einer geschützten Umgebung. Auch hier müssen HMAC,
Dateiarchive, Dateiliste und authentisierte Hauptschlüsselkopie vollständig vorliegen.
English: `--passphrase DUMP` performs the same strict full-set check for legacy
passphrase encryption, using independently supplied protected environment values.


## Hosthelper und getrenntes Buildbudget (FQ18)

Der sichere Auftragseingang, rootgeschützte Ergebnisordner, Release-Signaturprüfung,
Abstammungsprüfung und Abbruch bei unvollständigem Vorupdatebackup bleiben aktiv.
Die mitgelieferte systemd-Unit begrenzt nun den **Hosthelper samt direkten Kindprozessen**:
CPUQuota 100 % (zusammen eine logische CPU), MemoryHigh 512 MiB, MemoryMax 1 GiB,
TasksMax 128, Nice 10. Das sind konservative **Schätzwerte**, keine gemessene Dimensionierung
für einen bestimmten gemeinsam genutzten Server. Die CPU-/RAM-/PID-Abrechnung ist aktiv.
Ein Betreiber kann die Werte in einem rootgeschützten Drop-in unter
`/etc/systemd/system/hubiplan-aktualisierer@.service.d/ressourcen.conf` überschreiben:

```ini
[Service]
CPUQuota=100%
MemoryHigh=512M
MemoryMax=1G
TasksMax=128
```

Die Unit muss erst beim freigegebenen Deployment installiert und von systemd neu geladen
werden. Hier wurden weder Hostkonfiguration noch tatsächliche Cgroup-Zuordnung geprüft
oder geändert. Die lokale Regression prüft die ausgelieferte Konfiguration, keine reale
Durchsetzung auf einem Server. Kein ganzer Docker-/Hestia-Dienst darf hierfür pauschal
mitbegrenzt werden: Das würde auch andere Websites und Bestandscontainer betreffen.

**Offene Betriebsfreigabe:** Über den Docker-Socket angeforderte Builds laufen beim
Docker-Daemon bzw. BuildKit und erben die Helper-Unitlimits nicht. Die Compose-Laufzeitlimits
begrenzen ebenfalls keine Image-Builds. Für einen geteilten Host sind daher folgende
Optionen getrennt freizugeben:

- Empfehlung: geprüfte Images außerhalb des gemeinsam genutzten Webhosts bauen; der Host
  lädt nur freigegebene Fassungen. Registry-/Signatur-/Rollbackverfahren vorher festlegen.
- Alternativ: einen dedizierten begrenzten Builder mit passender Cgroup-/Docker-Treiber-
  Konfiguration provisionieren. Buildx bietet beim Container-Treiber CPU-/Speicheroptionen;
  PID-Gesamtgrenze und Zuordnung aller Buildprozesse müssen zusätzlich nachgewiesen werden.
- Bis dahin ein explizites Wartungsfenster mit Betreiberaufsicht; dies ist **kein** technischer
  Gesamtschutz und schließt den offenen Host-Buildteil von H01/FQ18 nicht.

CPU/RAM/PID-Gesamtreserve, Wartungsfenster, Freigabeverantwortliche und Umgang mit OOM/
Timeout müssen anhand des konkreten Hosts abgenommen werden. Keine Aktivierung oder
Deaktivierung von Selbstupdate wurde hier vorgenommen.

Die Grenzen folgen der offiziellen [systemd-Ressourcensteuerung](https://freedesktop.org/software/systemd/man/latest/systemd.resource-control.html).
Die getrennte Builder-Konfiguration beschreibt die [Docker-Dokumentation zum Container-Treiber](https://docs.docker.com/build/builders/drivers/docker-container/).

English: the shipped systemd unit now bounds the helper and its direct child processes.
Defaults (one logical CPU, 512 MiB memory high watermark, 1 GiB memory maximum, 128 tasks)
are conservative estimates and configurable through a root-owned unit drop-in. They do
not constrain work delegated to Docker/BuildKit. Host activation and an independently
bounded builder or external build/release process still require operational acceptance;
no server actions or live enforcement tests were performed.


### Bindung an den Sicherungssatz und Grenzen

Neue Sicherungskennungen enthalten Sekunden und einen Zufallsteil. Dump, Dateiarchiv,
Manifest, `datenschluessel_STAMP.age` bzw. `.enc` und `datenschluessel_STAMP.sha256`
gehören über dieselbe Kennung zusammen; verschlüsselte Dateien und Fingerabdruck tragen
je eine HMAC. Gleichzeitige Starter für denselben Backupordner werden mit `flock`
abgewiesen, ohne fremde temporäre Dateien oder Marker anzufassen. Schlüsselkopien und
Fingerabdrücke werden mit ihrem Satz aufbewahrt und an den zweiten Ort kopiert.

Für eine Übergangsfassung bleiben `datenschluessel.age`/`.enc` und `.sha256` als Kopie
**des letzten** Schlüssels erhalten. Sie dürfen niemals als Beweis für die Zugehörigkeit
zu einem älteren Dump verwendet werden. Strenge Prüfungen wählen ausschließlich die
zur Kennung passende Kopie. Der Schlüsselquellpfad ist standardmäßig das Docker-Secret
`/run/secrets/datenschluessel` (`BACKUP_DATA_KEY_FILE` kann ihn bei bewusst anderer
Schlüsselverwaltung ersetzen). Die Sicherung eines Schlüsselrings ersetzt keine Prüfung,
dass die Anwendung genau diesen Schlüsselring bzw. einen unabhängigen Provider verwendet.

Alte Dump-/Archivnamen bleiben lesbar. Ohne satzgebundenen Schlüssel/Fingerabdruck schlägt
`--age`/`--passphrase` kontrolliert fehl. Für die Prüfung der noch belegbaren Teile gibt es
explizit `--legacy-age DUMP IDENTITAET` und `--legacy-passphrase DUMP`. Diese Modi melden
**LEGACY-Teilprüfung (keine Schlüsselzuordnung)**, niemals einen vollständig geprüften Satz.
Die tägliche serverseitige SQL-/Datei-Vorprüfung bleibt davon getrennt. Ein strenger lokaler
Test scheitert auch bei fehlenden DB-Dateiverweisen; die geplante Sicherung behält wie bisher
den Unvollständigkeitsmerker und löscht dann keine alten Sicherungen.

Die lokale Teststrecke prüft zusätzlich mit synthetischen Daten einen SQL-Restore in eine
weitere Wegwerf-Datenbank und entschlüsselt dort gespeicherte Geburtsdaten sowie Rechnungs-/Rundschreibenkontakte
(E-Mail, Anschrift und JSON-Platzhalter) mit dem aus
**diesem** Sicherungssatz zurückgewonnenen Hauptschlüssel. Verglichen wird eine Prüfsumme
der entschlüsselten Werte, es werden keine Klartext-Personendaten ausgegeben. Getrennte
Regressionen vertauschen gültig verschlüsselte Schlüsselkopien, prüfen explizite Legacy-
Modi und verifizieren einen älteren Satz nach einer neueren Schlüsselringrotation.

**Das ist keine vollständige praktische Wiederanlaufübung.** MFA-Geheimnisse, Peering-
Signaturmaterial, Mail-/Meta-Zugänge, externe Schlüsselprovider und jede verschlüsselte
Datei wurden dadurch nicht in einer laufenden Gesamtanwendung wiederhergestellt.
Unabhängig zu verwahren und in einer freigegebenen lokalen Übung zuzuordnen sind insbesondere
Hauptschlüsselring/Providerzugang, `MFA_ENCRYPTION_KEYS`, Django-Geheimnis, Peering-Schlüssel,
Backup-HMAC-Schlüssel, private age-Identität und Restic-Zugangsmaterial sowie Löschliste und
Konfiguration. Kein privater age-Schlüssel gehört auf den Produktivserver. RPO/RTO,
Verantwortliche, Prüfintervall, externe Kopie und fachliche Vollständigkeit bleiben
betriebliche Abnahmen; ein positiver technischer Test nimmt sie nicht vorweg.

English: every new snapshot binds its own encrypted data-key ring and authenticated
fingerprint to the dump/archive identifier; strict restores never select the latest-key
compatibility alias. Old snapshot names remain readable via explicitly labelled partial
legacy verification. Tests cover key swapping, old-snapshot restoration after rotation,
and decrypting synthetic restored birth dates and billing/circular contact copies with the recovered snapshot key.
This does not establish a full application restart, MFA/peering recovery, external escrow
availability, or accepted RPO/RTO.


### Sicherheitszustand nach Rücksicherung (V06)

`auth_version` liegt selbst in der Datenbanksicherung. Nach dem Einspielen eines älteren
Stands ist der Wert **nicht über Rücksicherungen hinweg monoton**. Auch Geräte-/Peer-
Widerrufe, Kontosperren und Passwort-/MFA-Änderungen nach dem Sicherungszeitpunkt können
im restaurierten Datenbestand fehlen. Der Restore beweist deshalb nicht, dass spätere
Sicherheitsmaßnahmen weiterwirken. Alte Browser-Sessions oder Tokens dürfen daraus
keine erneute Freigabe erhalten.

Vor jeder Wiederfreigabe muss eine verantwortliche Betriebs-/Sicherheitsrolle den noch
isolierten Stand bewusst behandeln und den gewählten Weg protokollieren:

- **Option A, empfohlen bei unvollständigem unabhängigem Änderungsnachweis:** restaurierte
  Browser-Sessions und kurzlebige Anmelde-/Token-Caches in Datenbank, Redis und Prozessen
  verwerfen. Geräteanmeldungen und Peer-Anmeldungen prüfen und bei nicht belegbarem
  Widerrufsstand gezielt neu koppeln bzw. kontrolliert neu freigeben. Betroffene Konten
  bis zur Prüfung späterer Sperren und Passwort-/MFA-Änderungen nicht freigeben.
- **Option B, nur mit geprüft vollständigem unabhängigen Sicherheitsjournal:** alle nach
  dem Sicherungszeitpunkt erfolgten Sperren, Geräte-/Peer-Widerrufe und Passwort-/MFA-
  Sicherheitsänderungen im isolierten Stand abgleichen und nachführen. Sitzungen und
  kurzlebige Token-Caches ebenfalls verwerfen; gezieltes Neuvertrauen erst nach dokumentierter
  Vollständigkeitsprüfung. Das ältere Datenbankbackup selbst ist kein solcher Nachweis.

Der Betreiber verantwortet Abgleich, angemessene Benutzer-/Partnerinformation und die
Freigabe. Aktuelle Löschlisten und nachträgliche fachliche Sicherheitsentscheidungen sind
zusätzlich einzubeziehen. Peer-/Geräte-Neukopplungen sowie Passwort-/MFA-Maßnahmen brauchen
bewusste Einzelfall- bzw. Notfallfreigaben; die technische Satzprüfung führt keine
ungeprüften Massenresets aus. Wiederanlauf zunächst isoliert, Wiederfreigabe erst nach
abgeschlossenem Sitzungs-/Widerrufsabgleich. In dieser Änderung wurden keine produktiven
Daten zurückgesetzt oder Anmeldungen widerrufen.

English: `auth_version` and revocation state roll back with the database and are not
globally monotonic across restores. Before reopening a restored service, a responsible
operator must discard restored browser sessions and short-lived authentication caches,
and reconcile post-snapshot account blocks, device/peer revocations and password/MFA
security changes. Use independently verified complete security records or keep affected
access blocked and deliberately establish fresh trust. No automatic mass reset is
performed by the technical restore verifier.


Der lesbare Schlüsselring wird für jede Sicherung einmal in den geschützten WORK-/tmpfs-
Ordner kopiert. Verschlüsselung und Fingerabdruck entstehen aus genau dieser Kopie;
ein atomarer Austausch der Live-Datei dazwischen kann sie nicht auseinanderziehen.
Unlesbare oder fehlende Schlüsselquelle erzeugt einen Unvollständigkeitsmerker und
verhindert eine strenge vollständige Satzprüfung. Bei externen Providern muss statt
Exportpflicht auf dem Server ein bewusst freigegebenes unabhängiges Schlüssel-/Escrow-
Verfahren die Wiederherstellbarkeit belegen; die vorhandene lokale Dateiprüfung behauptet
für einen solchen Provider keine Vollständigkeit. Schlüsselrotation und Daten-/Datei-
Schnappschüsse benötigen weiterhin ein abgestimmtes Verfahren bzw. Wartungsfenster.
English: encryption and fingerprint use the same immutable tmpfs key-ring copy. An
unreadable/missing source is incomplete. External key providers need an independently
accepted recovery procedure; the file-based verifier does not certify them.

### Empfangs-/Kapazitätsbudgets im Verbund

Der Empfang reserviert atomar Kapazität, bevor Pakete oder Dateien gespeichert werden.
Dubletten derselben Nachrichtenkennung werden nicht erneut belastet. Jede neue
Nachricht zählt mindestens 64 KiB, sonst das Doppelte der UTF-8-JSON-Nutzdaten;
auch ersetzte Stände und veraltete Sequenzen verbrauchen Empfangskapazität. Dies ist
ein konservatives dauerhaftes Empfangsbudget, keine Anzeige exakt belegter Plattenbytes.
Bestehende Nachrichten und retained Dateien werden vor dem ersten Empfang mitgezählt.
Nicht lesbarer Altbestand blockiert den Empfang, bis er geprüft ist.

Standardgrenzen: Instanz 10 GiB/200000 Nachrichten, Empfängereinheit 2 GiB/50000,
Partnerinstanz über alle Empfänger 1 GiB/25000 sowie 1000 Nachrichten in 24 Stunden.
Bei Überschreitung wird vor der Verarbeitung mit 507 bzw. 429 abgelehnt. Die Kopplung
behält ihren bisherigen Sequenzstand; nach begründeter Kapazitätsfreigabe kann sie
wieder zustellen. Die API zeigt reservierte Bytes und Nachrichten je Kopplung unter
`reception_budget`; `initialized=false` bedeutet noch nicht vermessenen Altbestand.

Positive Umgebungswerte `PEERING_RECEPTION_INSTANCE_BYTES`,
`PEERING_RECEPTION_INSTANCE_MESSAGES`, `PEERING_RECEPTION_UNIT_BYTES`,
`PEERING_RECEPTION_UNIT_MESSAGES`, `PEERING_RECEPTION_PEER_BYTES`,
`PEERING_RECEPTION_PEER_MESSAGES`, `PEERING_RECEPTION_PEER_DAILY_MESSAGES`
ändern die Grenzen. Vor einer Erhöhung freie Host-/Volume-Kapazität und Aufbewahrung
prüfen und die Freigabe dokumentieren. Null bedeutet **nicht** unbegrenzt.
Reservierungen werden niemals automatisch zurückgesetzt; Rechnungen und Rundschreiben
werden nicht zur Quotenbereinigung gelöscht. Host-/Volumequoten und unabhängige
Kapazitätsalarme bleiben zusätzliche Betriebsmaßnahmen auf dem gemeinsamen Server.
Die Schemaerweiterung ist additiv; bei einem Rückweg zunächst nur den Code zurücknehmen,
die zusätzlichen Spalten eine Fassung lang stehen lassen.
