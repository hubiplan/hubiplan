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
- Den lokalen Port erreicht auf einem geteilten Server jeder Prozess. Deshalb schickt nginx
  zusätzlich einen geheimen Kopfwert `X-Hubiplan-Proxy` mit; nur damit übernimmt Caddy
  `X-Real-IP` (`HUBIPLAN_PROXY_GEHEIM` in der `.env`, `deploy/caddy/proxy-ip.caddy`).
  `deploy/hestia/einrichten.sh` richtet das ein. Bestehende Installationen: erst die Vorlagen
  erneuern (siehe unten), dann einmal

  ```powershell
  Get-Content -Raw deploy/hestia/proxy-geheim.sh | ssh deploy@server.example.org "sudo bash -s"
  ```

  Ohne `HUBIPLAN_PROXY_GEHEIM` verhält sich Caddy wie bisher.
- Auch die Container selbst erreicht auf einem geteilten Server jeder Prozess im Docker-Netz,
  an Caddy vorbei. Das Backend glaubt `X-Forwarded-For` deshalb nur, wenn die Verbindung von
  Caddy kommt, und die Besucheradresse der Vereinswebseite (`X-Hubiplan-Besucher`) nur vom
  Webseiten-Dienst. Wer sonst anfragt, zählt für alle Drosselungen mit der Adresse seiner
  Verbindung. Erkannt werden beide an ihrem Namen im Docker-Netz: `HUBIPLAN_PROXY_HOSTS`
  (Standard `web`) und `HUBIPLAN_WEBSITE_HOSTS` (Standard `website`); `docker-compose.server.yml`
  setzt beides, in der `.env` ist nichts einzutragen. Einzelheiten von `/api/health/` gibt es
  nur noch aus dem Backend-Container selbst, die Zertifikatsfrage `/api/intern/tls/` nur für Caddy.
  Grenzen: Datenbank und Redis bleiben für Prozesse auf dem Server erreichbar und sind durch
  ihre Passwörter geschützt. Läuft die Vereinswebseite auf einem anderen Server, teilen sich
  ihre Besucher weiterhin dessen Adresse.

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

## Weitere Adressen je Einheit

Ein Verein kann HUBIplan unter einer eigenen Adresse mit seinen Farben und seinem Wappen nutzen
(Plattform › Einstellungen › „Adressen je Einheit“, siehe [betrieb.md](betrieb.md)). Hinter
Hestia bekommt jede solche Adresse eine eigene Web-Domain mit der Vorlage `app-8110` und ein
eigenes Zertifikat, kein Alias der Hauptdomain: So hängt die Verlängerung des Hauptzertifikats
nicht an der DNS eines anderen Vereins.

```powershell
Get-Content -Raw deploy/hestia/adresse-hinzufuegen.sh | ssh deploy@server.example.org "sudo env HUSER=hosting-user DOMAIN=mitglieder.sv-musterstadt.example ZONE=sv-musterstadt.example bash -s"
```

Liegt die Zone in Hestia, legt das Skript den A-Eintrag an; sonst `ZONE=extern` angeben und
den Eintrag beim DNS-Anbieter setzen. Das Zertifikat holt es erst, wenn ein öffentlicher
Resolver die Adresse auf den Server auflöst; bis dahin das Skript später noch einmal starten.
Fehlt `HUBIPLAN_ADRESSEN_AUS_LISTE=1` in der `.env`, trägt es den Schalter ein (mit Sicherung);
er wirkt ab dem nächsten Ausrollen. Bis dahin und solange die Adresse in HUBIplan nicht
eingetragen ist, antwortet HUBIplan dort mit „Unbekannte Adresse“ (400). Mails gehen weiter
von der festen Absenderadresse aus und teilen sich deren Versandlimit.

## Eigene Änderungen und Quellcode (AGPL)

Die Seite `/lizenz` verlinkt den Quellcode der laufenden Fassung (AGPL § 13). Wer HUBIplan mit
eigenen Änderungen betreibt, muss seinen geänderten Quellcode genauso anbieten: den Stand in
einem öffentlichen Repository veröffentlichen und in der `.env` des Servers
`HUBIPLAN_SOURCE_URL=https://example.org/eigenes/hubiplan` setzen, dann neu ausrollen. Der Link
zeigt danach auf dieses Repository und den Commit der laufenden Fassung; der Commit muss dort
also vorhanden sein. Details: [lizenzen.md](lizenzen.md).

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

## Zweiter Server mit eigener Mail

So entsteht ein eigener Server, auf dem neben HUBIplan auch die ganze Mail einer Domain liegt:
Postfächer, Webmail, der Mailversand von HUBIplan, die Verteiler und der E-Rechnungseingang.
Hestia bringt Exim, Dovecot, Roundcube, SpamAssassin und ClamAV mit; Postfächer, Weiterleitungen
und DKIM werden im Hestia-Panel verwaltet. HUBIplan läuft wie oben hinter nginx. Alle Namen sind
Beispiele: Postfächer unter `example.org`, HUBIplan unter `verein.example.org`, Verteiler auf
`verein.example.org`, Mailserver `mail.example.org`, Webmail `webmail.example.org`.

Der Server hat keine Vertrauensstellung zu anderen Servern: eigener SSH-Schlüssel, eigener
age-Schlüssel, eigener Zugang zum Sicherungsort. Als Größe genügen für eine Domain etwa 4 vCPU,
8 GB RAM (plus 4 GB Swap) und 200 GB; HUBIplan braucht 3–4 GB, ClamAV gut 1 GB, Hestia mit
SpamAssassin etwa 2 GB.

### Ablauf

1. **Grundsystem:** frisches Debian in einer Fassung, die der Hestia-Installer unterstützt
   (vor der Bestellung prüfen), IPv4 und IPv6, kein vorinstalliertes Panel. System
   aktualisieren, unprivilegierten Admin-Benutzer mit `sudo` und SSH-Schlüssel anlegen,
   automatische Sicherheitsupdates (`unattended-upgrades`) mit nächtlichem Neustartfenster, Swap.
2. **Hestia installieren**, ohne Apache, FTP und DNS-Server (die Zone bleibt beim DNS-Anbieter),
   mit ClamAV und SpamAssassin. Der Rechnername ist ein eigener Name wie `server.example.org`,
   **nicht** `mail.example.org`: Diesen Namen braucht die Mail-Domain für ihr Zertifikat, sonst
   scheitert Let's Encrypt. Nach außen meldet sich Exim trotzdem mit dem Namen aus dem PTR
   (`mail.example.org`). Für den Rechnernamen A- und AAAA-Eintrag beim DNS-Anbieter anlegen.

   ```bash
   sudo bash hst-install.sh --hostname server.example.org --email adresse@example.org \
     --apache no --vsftpd no --proftpd no --named no --clamav yes --spamassassin yes
   ```

   Die übrigen Werte auf der Voreinstellung lassen und vor dem Lauf mit `bash hst-install.sh -h`
   abgleichen. Danach einen Hestia-Benutzer (`HUSER`) für die Domains anlegen. Ohne Apache
   ist nginx selbst der Webserver; `einrichten.sh`, `adresse-hinzufuegen.sh` und
   `vorlagen-erneuern.sh` erkennen das und legen die Vorlage `app-8110` dann unter
   `nginx/php-fpm` ab.

   **Eigener DNS-Resolver:** Spamhaus beantwortet keine Anfragen über große öffentliche
   Resolver (1.1.1.1, 8.8.8.8) und meldet dann „open resolver“; Exim weist daraufhin jede
   eingehende Mail ab. Deshalb `unbound` installieren und `/etc/resolv.conf` darauf zeigen
   lassen:

   ```bash
   sudo apt install -y unbound
   sudo rm /etc/resolv.conf
   printf 'nameserver 127.0.0.1\noptions edns0 trust-ad\n' | sudo tee /etc/resolv.conf
   dig +short 2.0.0.127.zen.spamhaus.org   # Testeintrag: 127.0.0.x
   ```

   Hestia legt `freshclam` bei der Installation nicht immer als Dienst an:
   `sudo systemctl enable --now clamav-freshclam`.
3. **Härten** wie unter [Server härten](#server-härten), dazu die Punkte unten.
4. **DNS** wie unten anlegen, zunächst ohne MX. PTR setzen lassen.
5. **Mail-Domain** `example.org` im Panel anlegen (Spam- und Virenprüfung an, DKIM an,
   Webmail Roundcube), Let's Encrypt für die Mail-Domain einschalten (deckt `mail.` und
   `webmail.` ab), Postfächer mit Quote (z. B. 2–5 GB) und starken Einzelpasswörtern anlegen.
6. **Proben:** Mail an große Anbieter senden und in den Kopfzeilen SPF, DKIM und DMARC `pass`
   prüfen, Empfang von außen, Mailprogramm am Handy, Webmail. Die IP vorher auf Sperrlisten
   prüfen und klären, dass Port 25 ausgehend offen ist.
7. **MX umstellen.** Bisherige Postfächer der Domain auf dem neuen Server anlegen (bei Bedarf
   Inhalte mit `imapsync` übernehmen).
8. **HUBIplan** wie unter [Erstes Einrichten](#erstes-einrichten) ausrollen und einrichten. Weil
   die Zone nicht in Hestia liegt, `DNS=extern` mitgeben, und das Versandpostfach heißt hier
   meist `noreply`:

   ```powershell
   Get-Content -Raw deploy/hestia/einrichten.sh | ssh deploy@server.example.org "sudo env HUSER=hosting-user DOMAIN=verein.example.org MAILDOMAIN=example.org MAILKONTO=noreply DNS=extern ALARM_MAIL=adresse@example.org bash -s"
   ```

   Die Mail-Domain `example.org` muss dafür schon existieren. HUBIplan versendet dann über
   `mail.example.org`, wie auf einem Server mit fremder Mail.
9. **Verteiler** einrichten (Catch-all nur auf `verein.example.org`, damit Tippfehler an
   `example.org` nicht im Sammelpostfach landen):

   ```powershell
   Get-Content -Raw deploy/hestia/verteiler.sh | ssh deploy@server.example.org "sudo env HUSER=hosting-user DOMAIN=verein.example.org ZONE=example.org DNS=extern bash -s"
   ```

   Für den E-Rechnungseingang ein eigenes **Rechnungspostfach** anlegen; das Skript schreibt
   die IMAP-Daten (`EINVOICE_IMAP_*`) in die `.env` (siehe [e-rechnungen.md](e-rechnungen.md)):

   ```powershell
   Get-Content -Raw deploy/hestia/rechnungspostfach.sh | ssh deploy@server.example.org "sudo env HUSER=hosting-user DOMAIN=example.org bash -s"
   ```
10. **Virenprüfung:** Der clamd von Hestia läuft schon. In der `.env`
    `CLAMD_SOCKET_DIR=/run/clamav` setzen; `docker-compose.clamav.yml` schaltet dann
    `VIRUS_SCAN_REQUIRED=1` ein (siehe [betrieb.md](betrieb.md)).
11. **Sicherung** wie unten einrichten und eine Wiederherstellung proben, bevor echte Daten
    kommen.

`MAIL_AUTHSERV_ID` bleibt hier leer: Exim schreibt keinen eigenen `Authentication-Results`-Kopf,
eine gesetzte Kennung würde also einem mitgeschickten fremden Kopf vertrauen. Verteiler-Mails
gehen deshalb immer mit Bestätigungslink hinaus (siehe [rundschreiben.md](rundschreiben.md)).

### DNS

Beim DNS-Anbieter, vorher die TTL auf 300 s senken und nach dem Umzug wieder erhöhen:

| Name | Typ | Inhalt |
|---|---|---|
| `verein.example.org`, `webmail.example.org`, `mail.example.org` | A / AAAA | IP des Servers |
| `example.org`, `verein.example.org` | MX | `10 mail.example.org` |
| `example.org`, `verein.example.org` | TXT | `v=spf1 mx -all` |
| `<selektor>._domainkey.example.org` | TXT | DKIM-Schlüssel aus dem Hestia-Panel (Mail-Domain › DNS) |
| `_dmarc.example.org` | TXT | zuerst `v=DMARC1; p=quarantine; rua=mailto:…`, nach 2–4 Wochen ohne Auffälligkeiten `p=reject` |
| `autoconfig.example.org`, `autodiscover.example.org` | CNAME | `mail.example.org` |
| `_imaps._tcp.example.org`, `_submissions._tcp.example.org` | SRV | `mail.example.org`, Port 993 bzw. 465 |

Die PTR-Einträge (Rückwärtsauflösung) von IPv4 und IPv6 zeigen auf `mail.example.org` und
passen damit zum A-Eintrag und zum HELO von Exim. Ohne passenden PTR landen Mails bei vielen
Anbietern im Spam. Optional MTA-STS und TLS-Berichte (`mta-sts.`, `_mta-sts`, `_smtp._tls`).

Zieht die Domain von einem anderen Hestia-Server um, dort nach dem Umschalten die Web- und
die Mail-Domain löschen. Sonst stellt der alte Server Mails seiner eigenen Nutzer an diese
Domain weiter lokal zu.

### Härtung mit Mail

Zusätzlich zu `deploy/hestia/haerten.sh` (alle Punkte, also auch `api` und `panel`):

- Offen nur 22, 80, 443, 25, 465, 587 und 993. POP3 (110, 995) und IMAP ohne TLS (143), FTP,
  Datenbank und Redis bleiben zu (Hestia-Firewall; davor die Firewall des Anbieters, falls
  vorhanden). Das Panel (8083) nur über SSH-Tunnel.
- Docker umgeht die Hestia-Firewall. HUBIplan hinter Hestia veröffentlicht nur
  `127.0.0.1:${WEB_PORT}`; keine weiteren Ports veröffentlichen.
- fail2ban (bringt Hestia mit) für SSH, Exim, Dovecot und Roundcube prüfen. Die Roundcube-Sperre
  ist zunächst aus (`[roundcube-auth]` in `/etc/fail2ban/jail.local`). Vor dem Einschalten
  `/var/log/roundcube/errors.log` mit Besitzer und Gruppe des Ordners anlegen, sonst startet
  fail2ban gar nicht. Die Hestia-Firewall regelt nur IPv4; für IPv6 eine eigene nftables-Tabelle
  mit denselben offenen Ports anlegen (ohne `flush ruleset`, das löschte auch die Hestia-Regeln).
- 2FA für das Panel, für das Konto beim Server- und DNS-Anbieter, beim Sicherungsanbieter und
  in Roundcube (Plugin `twofactor_gauthenticator`). Mailprogramme nutzen starke
  Einzelpasswörter je Postfach.
- In der `.env` von HUBIplan `SECURITY_ALERT_EMAIL`, `HUBIPLAN_SOURCE_URL` und
  `MAIL_RATE_PER_HOUR` passend setzen; `HUBIPLAN_PROXY_GEHEIM` legt `einrichten.sh` an.

### Sicherung mit Mail

Die Mail ist so wichtig wie die Vereinsdaten und gehört an denselben zweiten Ort.
`deploy/hestia/hubiplan-restic-backup.sh` sichert sie mit, wenn beim Einrichten der
Hestia-Benutzer genannt wird:

```powershell
Get-Content -Raw deploy/hestia/hubiplan-restic-backup.sh | ssh deploy@server.example.org "sudo tee /usr/local/sbin/hubiplan-restic-backup.sh >/dev/null && sudo chmod 700 /usr/local/sbin/hubiplan-restic-backup.sh && sudo env HUSER=hosting-user /usr/local/sbin/hubiplan-restic-backup.sh einrichten"
```

Das Skript trägt dann in `/root/.config/restic/hubiplan.mail` die Postfächer
(`/home/<HUSER>/mail`), die Mail-Einstellungen mit Kennwörtern und DKIM-Schlüsseln
(`/home/<HUSER>/conf/mail`) und die Panel-Einträge (`/usr/local/hestia/data/users/<HUSER>`) ein
und sichert sie täglich als eigene Snapshots mit dem Tag `mail`. Die HUBIplan-Sicherungen
bleiben unter dem Tag `hubiplan`, Aufbewahrung und Rücksicherung wie oben. Am Monatsersten holt
es zusätzlich einige ältere Mails zurück und vergleicht sie mit dem Original. Bestehende
Einrichtungen können `einrichten` auf diese Weise noch einmal aufrufen; Passwort und
Repository bleiben.

Die Mail liegt am Sicherungsort nur mit dem restic-Passwort verschlüsselt (die
HUBIplan-Sicherungen zusätzlich mit age). Das restic-Passwort deshalb wie den age-Schlüssel
außerhalb des Servers verwahren, im Passwortmanager und offline.

- **Zweiter Ort:** ein eigener SFTP-Zugang nur für diesen Server (z. B. Unterkonto einer
  Storage Box). Keine Sicherung nur beim Anbieter des Servers selbst.
- **Dritte Kopie, unveränderbar:** Ein übernommener Server kann mit seinem Zugang auch die
  restic-Kopie löschen. Dagegen hilft ein Ort, auf den der Server nicht löschend zugreift,
  zum Beispiel vom Anbieter des Speichers verwaltete Snapshots, die der Unterzugang nicht
  ändern kann, oder ein Speicher mit Object Lock. Das richtet das Skript nicht ein; Ziel und
  Aufbewahrung gehören in die privaten Wiederherstellungsunterlagen.
- **Wiederherstellung eines Postfachs** (als root, damit Eigentümer und Rechte erhalten
  bleiben; Repository wie in der eigenen Einrichtung):

  ```bash
  sudo env RESTIC_REPOSITORY=sftp:storagebox:restic-hubiplan RESTIC_PASSWORD_FILE=/root/.config/restic/hubiplan.pass \
    restic restore latest --tag mail --include /home/hosting-user/mail/example.org/vorstand --target /var/tmp/mail-zurueck
  sudo cp -a /var/tmp/mail-zurueck/home/hosting-user/mail/example.org/vorstand/. /home/hosting-user/mail/example.org/vorstand/
  sudo rm -rf /var/tmp/mail-zurueck
  ```

  Vorhandene Mails bleiben dabei, zurückgeholte kommen dazu.

  Für einen neuen Server zuerst Hestia, den Benutzer und die Mail-Domain anlegen, dann
  Postfächer und `conf/mail` zurückholen; `/usr/local/hestia/data/users/<HUSER>` dient als
  Nachschlag für Postfächer, Quoten und Weiterleitungen.
- Vor dem Start einmal vollständig zurückholen und prüfen, danach regelmäßig.
