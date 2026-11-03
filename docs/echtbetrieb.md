# Betrieb hinter einem vorhandenen Webserver

Diese Anleitung beschreibt eine beispielhafte Installation mit HestiaCP und nginx.
Server, Benutzer, Domains, Portbelegung, Sicherungsziele und Zeitpläne werden je Installation
festgelegt und nur in privaten Betriebsunterlagen dokumentiert. Alle folgenden Werte sind Beispiele.
Neue Stände zuerst lokal prüfen und auf einem Testserver mit erfundenen Daten erproben.

## Aufbau

nginx übernimmt HTTPS und leitet an Caddy auf `127.0.0.1:8110` weiter. Der interne Port ist
über `WEB_PORT` konfigurierbar und muss zur nginx-Vorlage passen. Die Anwendung belegt so
nicht selbst Port 80 oder 443. Die konkrete Belegung anderer Dienste gehört nicht in dieses Repository.

- `docker-compose.proxy.yml` bindet Caddy nur an `127.0.0.1:${WEB_PORT}` und verwendet
  `deploy/Caddyfile.proxy` (HTTP hinter dem TLS-Proxy).
- `HUBIPLAN_HINTER_PROXY=1` aktiviert diese Compose-Ergänzung beim Einrichten.
- nginx setzt `X-Real-IP`; Caddy reicht die Besucheradresse als einzelnen
  `X-Forwarded-For`-Eintrag weiter.

## Erstes Einrichten

SSH-Ziel und Schlüssel werden ausschließlich lokal konfiguriert. Die Beispiele setzen einen
Benutzer mit `sudo` voraus; er kann von dem Hestia-Benutzer `HUSER` abweichen. Die Hestia-Skripte
verlangen `HUSER` ausdrücklich und brechen ohne diesen Wert vor Änderungen ab.

1. Lokal `scripts/test.sh` ausführen (siehe [testserver.md](testserver.md)).
2. Ein Backup-Schlüsselpaar auf einem vertrauenswürdigen lokalen Rechner erzeugen
   (`age-keygen`, siehe [betrieb.md](betrieb.md)). Der private Schlüssel bleibt außerhalb des Servers.
3. Ausrollen; neue Schlüssel werden auf dem Server in `/opt/hubiplan/.env` angelegt:

   ```bash
   DEPLOY_HOST=deploy@server.example.org DEPLOY_SUDO=1 SITE_HOST=verein.example.org HUBIPLAN_HINTER_PROXY=1 BACKUP_PUBLIC_KEY=age1… deploy/deploy.sh
   ```

   `SITE_HOST`, `HUBIPLAN_HINTER_PROXY` und `WEB_PORT` gelten beim ersten Einrichten;
   danach bestimmt die serverseitige `.env` die Werte.
4. Web-Domain, DNS, Zertifikat und SMTP-Postfach einrichten:

   ```powershell
   Get-Content -Raw deploy/hestia/einrichten.sh | ssh deploy@server.example.org "sudo env HUSER=hosting-user DOMAIN=verein.example.org MAILDOMAIN=example.org ALARM_MAIL=adresse@example.org bash -s"
   ```

   Bei noch nicht verbreiteten DNS-Änderungen vorübergehend `OHNE_ZERTIFIKAT=1` setzen
   und den Aufruf nach der DNS-Verbreitung ohne diese Option wiederholen.
5. Schlüssel und Wiederherstellungsunterlagen getrennt vom Server sicher verwahren.
6. Den ersten Plattform-Zugang interaktiv anlegen:

   ```bash
   ssh -t deploy@server.example.org "cd /opt/hubiplan && sudo docker compose -f docker-compose.server.yml -f docker-compose.proxy.yml exec backend python manage.py createsuperuser"
   ```

   Anschließend 2FA einrichten sowie Impressum und Datenschutzhinweise ausfüllen.
7. Den Server härten, bevor echte Mitgliederdaten verarbeitet werden. Keine Demodaten
   mit `seed_testdata` auf produktiven Instanzen anlegen.

## Ausrollen und Vorlagen erneuern

```bash
DEPLOY_HOST=deploy@server.example.org DEPLOY_SUDO=1 deploy/deploy.sh
```

Nach Änderungen an nginx-Vorlagen die Vorlagen beider Anwendungen neu einspielen:

```powershell
Get-Content -Raw deploy/hestia/vorlagen-erneuern.sh | ssh deploy@server.example.org "sudo env HUSER=hosting-user bash -s"
```

Das Skript prüft mit `nginx -t` und stellt bei Fehlern die vorigen Vorlagen wieder her.
Manuelle Compose-Aufrufe auf dieser Installation benötigen beide Compose-Dateien:

```bash
sudo docker compose -f docker-compose.server.yml -f docker-compose.proxy.yml ps
```

## Mailversand und Verteiler

SMTP-Zugang und Versandgrenzen werden je Installation in der `.env` hinterlegt.
`MAIL_RATE_PER_HOUR` muss zum Limit des eigenen Mailanbieters passen. Verteiler werden
über einen eigenen Domain-/Catch-all-Postfach-Aufbau eingerichtet:

```powershell
Get-Content -Raw deploy/hestia/verteiler.sh | ssh deploy@server.example.org "sudo env HUSER=hosting-user DOMAIN=verein.example.org ZONE=example.org bash -s"
```

DNS-Änderungen müssen überall angekommen sein, bevor der Verteiler verwendet wird.
Weitere Hinweise: [rundschreiben.md](rundschreiben.md).

## Sicherung und Wiederherstellung

HUBIplan benötigt verschlüsselte Sicherungen, einen getrennten zweiten Sicherungsort und
regelmäßige Wiederherstellungsproben (siehe [betrieb.md](betrieb.md)). Das Hestia-Skript
`deploy/hestia/hubiplan-restic-backup.sh` ist eine optionale Vorlage für die zusätzliche
restic-Kopie. SSH-Zugang, `RESTIC_REPOSITORY`, Alarmempfänger und Zeitplan vor dem Einrichten
an die eigene Installation anpassen. Der voreingestellte Zeitplan ist ein Beispiel;
die Kopie muss nach der Anwendungssicherung laufen.

```powershell
Get-Content -Raw deploy/hestia/hubiplan-restic-backup.sh | ssh deploy@server.example.org "sudo tee /usr/local/sbin/hubiplan-restic-backup.sh >/dev/null && sudo chmod 700 /usr/local/sbin/hubiplan-restic-backup.sh && sudo /usr/local/sbin/hubiplan-restic-backup.sh einrichten"
```

Die lokalen Wiederherstellungsunterlagen enthalten das tatsächliche Sicherungsziel,
Zugänge, Schlüsselverwahrung, Aufbewahrung und Zuständigkeiten. Private Schlüssel und
Passwörter gehören nicht ins Repository. Zusätzlichen Schutz gegen das Löschen der Kopie
bieten unabhängig verwaltete Snapshots oder ein unveränderbarer Sicherungsort.

Das beim Einrichten erzeugte restic-Passwort steht standardmäßig in
`/root/.config/restic/hubiplan.pass`. Zusätzlich außerhalb des Servers sicher verwahren;
für die Wiederherstellung nach einem Totalverlust werden es und der Zugang zum zweiten
Sicherungsort benötigt. Auf einem vertrauenswürdigen Wiederherstellungsrechner beispielsweise:

```bash
export RESTIC_REPOSITORY=sftp:backup@backup.example.org:/backups/hubiplan
export RESTIC_PASSWORD_FILE="$HOME/.config/hubiplan/restic-passwort"
restic restore latest --tag hubiplan --target ./wiederherstellung
```

Die Datei in `RESTIC_PASSWORD_FILE` enthält die sicher verwahrte Kopie des restic-Passworts.
Danach die zurückgeholten Anwendungssicherungen mit dem getrennt verwahrten age-Schlüssel
entschlüsseln und wie in [betrieb.md](betrieb.md) beschrieben einspielen. Ziel und lokale
Passwortdatei im Beispiel durch die Werte aus den privaten Wiederherstellungsunterlagen ersetzen.

## Server härten

`deploy/hestia/haerten.sh` prüft die Hestia-/SSH-Konfiguration zunächst ohne Änderungen.
Einzelne Maßnahmen werden erst mit `PUNKT=ssh`, `api`, `panel` oder `aide` umgesetzt.
`ADMIN_USER` muss den tatsächlichen, unprivilegierten SSH-Administrator angeben;
dieser kann vom Hestia-Benutzer `HUSER` abweichen.

```powershell
Get-Content -Raw deploy/hestia/haerten.sh | ssh deploy@server.example.org "sudo env ADMIN_USER=deploy bash -s"
```

Nach einer SSH-Änderung die Anmeldung sofort in einer zweiten Sitzung prüfen.
2FA für Panel-Konten im Hestia-Panel aktivieren.
