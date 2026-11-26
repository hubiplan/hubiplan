#!/bin/bash
# Optionale zweite Backup-Kopie: überträgt verschlüsselte Anwendungssicherungen
# und die .env (darin nur durch das restic-Passwort geschützt) per restic auf einen
# getrennten Speicher (SFTP oder rest-server). Zugang und Ziel werden je Installation
# lokal auf dem Server konfiguriert.
#
# Liegt auch die Mail auf dem Server (Hestia mit Exim/Dovecot), sichert das Skript
# zusätzlich die Postfächer und die Mail-Einstellungen des Hestia-Benutzers, als eigene
# Snapshots mit dem Tag „mail“. Dafür beim Einrichten HUSER angeben (siehe unten); die
# Pfade stehen danach in MAILPFADE (eine Zeile je Pfad, nur auf dem Server).
#
# Einrichten (einmal, vom lokalen Arbeitsrechner in PowerShell):
#   Get-Content -Raw deploy\hestia\hubiplan-restic-backup.sh | ssh deploy@server.example.org "sudo tee /usr/local/sbin/hubiplan-restic-backup.sh >/dev/null && sudo chmod 700 /usr/local/sbin/hubiplan-restic-backup.sh && sudo /usr/local/sbin/hubiplan-restic-backup.sh einrichten"
#
# Mit Mail: im letzten Befehl „sudo env HUSER=hosting-user /usr/local/sbin/…“ schreiben.
# Bestehende Einrichtungen können „einrichten“ so noch einmal aufrufen; Passwort und
# Repository bleiben, nur die Mailpfade kommen dazu.
#
# „einrichten“ legt bei Bedarf ein eigenes restic-Passwort an (nur auf dem Server, Datei
# siehe PASSDATEI), legt das Repository an, schreibt /etc/cron.d/hubiplan-restic und
# macht eine erste Sicherung. Das Passwort danach zusätzlich im Passwortmanager ablegen,
# sonst ist die Kopie bei einem Totalausfall des Servers nicht lesbar.
#
# Fehlermeldungen gehen an die Adresse in /root/.config/restic/hubiplan.mailto (sonst root):
#   echo adresse@example.org | ssh deploy@server.example.org "sudo tee /root/.config/restic/hubiplan.mailto"
#
# Einstellungen (optional) in /root/.config/restic/hubiplan.conf (Rechte 600), als
# Shell-Zuweisungen; alle Werte gehen als Umgebung an restic (Gesamtaudit 15.11., OPS-06):
#   RESTIC_REPOSITORY=rest:https://backup.example.org/hubiplan/   (oder sftp:…)
#   RESTIC_REST_USERNAME=…  RESTIC_REST_PASSWORD=…   eigener Zugang zum rest-server
#   RESTIC_CACERT=/root/.config/restic/ca.pem        nur bei eigener Zertifizierungsstelle
#   RESTIC_AUFBEWAHRUNG=aus   Standard „an“: forget/prune täglich hier auf dem Server.
#                             „aus“: hier nur sichern, prüfen, Probe und Speicherstand;
#                             forget/prune mit „aufbewahrung“ von einem getrennten Rechner.
#   RESTIC_WARNGRENZE_GB=200  nur bei „aus“: WARNUNG im Protokoll, wenn die Kopie größer ist
#
# Ohne Argument: Sicherung (so ruft cron es täglich auf). Gibt keine Passwörter aus.
# „aufbewahrung“: forget/prune und check, gedacht für einen getrennten Rechner mit eigenem
# Zugang zum Speicher (dort dasselbe Skript und eine eigene hubiplan.conf/hubiplan.pass).
set -u
# Nur für die Skriptprüfung (scripts/pruefe-zweitort.sh): Wurzel aller Pfade und Ordner mit
# Befehlsersatz. Im Betrieb leer.
R=${HUBIPLAN_RESTIC_TESTWURZEL:-}
export PATH=${R:+$R/bin:}/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

export RESTIC_CACHE_DIR=$R/root/.cache/restic
export RESTIC_PASSWORD_FILE=$R/root/.config/restic/hubiplan.pass
KONFDATEI=$R/root/.config/restic/hubiplan.conf
if [ -r "$KONFDATEI" ]; then
    # D-M02: Konfigurationsdatei vor source auf Typ, Eigentümer und Schreibschutz prüfen
    if [ -L "$KONFDATEI" ] || [ ! -f "$KONFDATEI" ]; then
        echo "FEHLER: $KONFDATEI ist keine reguläre Datei" >&2
        exit 1
    fi
    konf_uid=$(stat -c '%u' "$KONFDATEI" 2>/dev/null || echo -1)
    konf_mode=$(stat -c '%a' "$KONFDATEI" 2>/dev/null || echo 777)
    if [ "$konf_uid" != "$(id -u)" ] && [ "$konf_uid" != 0 ]; then
        echo "FEHLER: $KONFDATEI gehört nicht root oder dem aktuellen Benutzer" >&2
        exit 1
    fi
    if [ $(( 8#$konf_mode & 8#022 )) -ne 0 ]; then
        echo "FEHLER: $KONFDATEI ist für Gruppe oder andere beschreibbar (Modus $konf_mode)" >&2
        exit 1
    fi
    set -a
    # shellcheck disable=SC1090
    . "$KONFDATEI"
    set +a
fi
PASSDATEI=$RESTIC_PASSWORD_FILE
export RESTIC_REPOSITORY=${RESTIC_REPOSITORY:-sftp:storagebox:restic-hubiplan}
# Sicherer Standard (D-M02): am Server nur anhängen, forget/prune von getrenntem Rechner
AUFBEWAHRUNG=${RESTIC_AUFBEWAHRUNG:-aus}
WARNGRENZE_GB=${RESTIC_WARNGRENZE_GB:-}
# Empfänger der Fehlermeldungen: eine Adresse in MAILDATEI (nur auf dem Server), sonst root
MAILDATEI=$R/root/.config/restic/hubiplan.mailto
MAILTO=${MAILTO:-$(head -n1 "$MAILDATEI" 2>/dev/null || echo root)}
LOG=$R/var/log/hubiplan-restic.log
BACKUPS=$R/opt/hubiplan-backups
ENVDATEI=$R/opt/hubiplan/.env
CRON=$R/etc/cron.d/hubiplan-restic
SPERRE=$R/run/hubiplan-restic.lock
STAND=$R/var/lib
# Zusätzlich zu sichernde Mailpfade, eine Zeile je Pfad; fehlt die Datei, keine Mailsicherung
MAILPFADE=$R/root/.config/restic/hubiplan.mail

log() { echo "$(date '+%F %T') $*" | tee -a "$LOG" >> "${REP:-/dev/null}"; }

# Hestia legt Postfächer unter /home/<benutzer>/mail/<domain>/<postfach> ab (Maildir),
# Kennwörter, Weiterleitungen und DKIM-Schlüssel unter /home/<benutzer>/conf/mail und die
# Einträge des Panels unter /usr/local/hestia/data/users/<benutzer>.
mailpfade_anlegen() {
    local p
    [ -n "${HUSER:-}" ] || return 0
    case "$HUSER" in *[!a-z0-9_-]*|"") echo "HUSER ungültig: $HUSER"; exit 1 ;; esac
    [ -d "/home/$HUSER/mail" ] || { echo "FEHLER: /home/$HUSER/mail fehlt (Mail-Domain in Hestia angelegt?)"; exit 1; }
    install -d -m 700 "$(dirname "$MAILPFADE")"
    (umask 077 && for p in "/home/$HUSER/mail" "/home/$HUSER/conf/mail" "/usr/local/hestia/data/users/$HUSER"; do
        [ -e "$p" ] && echo "$p"
    done > "$MAILPFADE")
    echo "Mailsicherung eingerichtet: $MAILPFADE"
    sed 's/^/  /' "$MAILPFADE"
}

mailpfade() { [ -s "$MAILPFADE" ] && grep -v '^[[:space:]]*\(#\|$\)' "$MAILPFADE"; }

einrichten() {
    command -v restic >/dev/null || { echo "restic fehlt (apt install restic)"; exit 1; }
    case "$RESTIC_REPOSITORY" in
        rest:http://*) echo "FEHLER: rest-server nur über https (rest:https://…)"; exit 1 ;;
    esac
    if [ ! -s "$PASSDATEI" ]; then
        install -d -m 700 "$(dirname "$PASSDATEI")"
        (umask 077 && openssl rand -base64 33 | tr -d '\n' > "$PASSDATEI")
        echo "Neues restic-Passwort angelegt: $PASSDATEI"
        echo "  -> bitte in den Passwortmanager übernehmen (sudo cat $PASSDATEI)"
    fi
    chmod 600 "$PASSDATEI"
    mailpfade_anlegen
    if restic cat config >/dev/null 2>&1; then
        echo "Repository $RESTIC_REPOSITORY gibt es schon."
    else
        restic init || { echo "FEHLER: restic init"; exit 1; }
    fi
    # Das HUBIplan-Backup läuft um 03:15 (Europe/Berlin) samt Rücksicherungstest;
    # die Kopie danach um 04:30 deutscher Zeit (cron läuft auf UTC, daher die Prüfung)
    cat > "$CRON" <<'EOF'
# HUBIplan-Backups (restic -> SFTP-Speicher) täglich 04:30 deutscher Zeit
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
MAILTO=root
30 2,3 * * * root [ "$(TZ=Europe/Berlin date +\%H)" = "04" ] && /usr/local/sbin/hubiplan-restic-backup.sh >/dev/null 2>&1
EOF
    chmod 644 "$CRON"
    echo "Zeitplan: $CRON"
    if [ "$AUFBEWAHRUNG" = aus ]; then
        echo "Aufbewahrung am Server aus: forget/prune mit „aufbewahrung“ von einem getrennten Rechner"
    fi
    sichern
    echo "Ergebnis: $(tail -n 1 "$LOG")"
}

# Monatliche Probe (Fachfrage 15, Audit 31.10.): das neueste Datenbank-Backup und seine
# Dateiliste vom Sicherungsort zurückholen und Byte für Byte mit dem Original vergleichen.
# Zeigt, dass die Kopie vollständig übertragen und mit dem restic-Passwort lesbar ist.
# (Entschlüsseln geht nur mit dem age-Schlüssel auf einem lokalen Arbeitsrechner; das prüft der tägliche
# Rücksicherungstest vor dem Verschlüsseln.)
probe() {
    local neu ziel name ok=0
    neu=$(ls -1t "$BACKUPS"/db_*.sql.gz.age 2>/dev/null | head -n 1)
    [ -n "$neu" ] || { log "FEHLER: Probe: kein Datenbank-Backup gefunden"; return 1; }
    name=$(basename "$neu")
    ziel=$(mktemp -d)
    if restic restore latest --tag hubiplan --target "$ziel" \
        --include "$BACKUPS/$name" --include "$BACKUPS/$name.hmac" \
        --include "$BACKUPS/dateien_*.sha256.age" -q >> "$LOG" 2>&1; then
        for f in "$neu" "$neu.hmac"; do
            [ -e "$f" ] || continue
            cmp -s "$f" "$ziel$f" || { log "FEHLER: Probe: $(basename "$f") weicht ab"; ok=1; }
        done
        listen=$(find "$ziel$BACKUPS" -name 'dateien_*.sha256.age' 2>/dev/null | wc -l)
        [ "$ok" = 0 ] && log "Probe ok: $name vom Sicherungsort zurückgeholt und gleich ($listen Dateilisten)"
    else
        log "FEHLER: Probe: restic restore"
        ok=1
    fi
    rm -rf "$ziel"
    return $ok
}

# Monatliche Probe der Mailsicherung: einige ältere Mails (ändern sich im Maildir nicht
# mehr) aus dem neuesten Mail-Snapshot zurückholen und mit dem Original vergleichen. Mails,
# die seit der Sicherung gelöscht oder verschoben wurden, zählen nicht als Fehler.
probe_mail() {
    local ziel f n=0 ok=0 args=()
    mapfile -t stichprobe < <(mailpfade | while read -r p; do
        find "$p" -type f -path '*/cur/*' -mtime +2 2>/dev/null
    done | shuf -n 5 2>/dev/null)
    [ "${#stichprobe[@]}" -gt 0 ] || { log "Mail-Probe: noch keine älteren Mails, übersprungen"; return 0; }
    for f in "${stichprobe[@]}"; do args+=(--include "$f"); done
    ziel=$(mktemp -d)
    if restic restore latest --tag mail --host "$(hostname -f)" --target "$ziel" "${args[@]}" -q >> "$LOG" 2>&1; then
        for f in "${stichprobe[@]}"; do
            if [ -e "$ziel$f" ]; then
                cmp -s "$f" "$ziel$f" && n=$((n + 1)) || { log "FEHLER: Mail-Probe: $f weicht ab"; ok=1; }
            elif [ -e "$f" ]; then
                log "FEHLER: Mail-Probe: $f fehlt in der Sicherung"; ok=1
            fi
        done
        [ "$ok" = 0 ] && log "Mail-Probe ok: $n Mails vom Sicherungsort zurückgeholt und gleich"
    else
        log "FEHLER: Mail-Probe: restic restore"
        ok=1
    fi
    rm -rf "$ziel"
    return $ok
}

# Aufbewahrung: alte Snapshots vergessen und Speicher freigeben. Braucht Löschrechte am
# Speicher; ein rest-server mit --append-only lehnt das ab.
vergessen() {
    restic forget --tag hubiplan --tag mail --keep-daily 14 --keep-weekly 8 --keep-monthly 12 \
        --group-by host,tags --prune -q >> "$LOG" 2>&1 \
        && log "Aufbewahrung/prune ok" || { log "FEHLER: forget/prune"; return 1; }
}

# Löscht der Server selbst am Zweitort (forget/prune), steht das höchstens einmal am Tag als
# HINWEIS im Protokoll. Kein Fehler: ändert weder FEHLER noch last-ok noch den Mailbetreff.
# RESTIC_SNAPSHOTS_AM_SPEICHER=ja (in hubiplan.conf): Am Speicher sind Snapshots eingerichtet,
# die der Server nicht löschen kann; dann entfällt der Hinweis.
hinweis_loeschend() {
    [ "${RESTIC_SNAPSHOTS_AM_SPEICHER:-}" != ja ] || return 0
    local heute
    heute=$(date +%F)
    [ "$(cat "$STAND/hubiplan-restic.hinweis" 2>/dev/null)" != "$heute" ] || return 0
    echo "$heute" > "$STAND/hubiplan-restic.hinweis" 2>/dev/null || true
    log "HINWEIS: forget/prune läuft auf diesem Server; wer ihn übernimmt, kann damit auch die Kopien löschen. Schutz: Snapshots am Speicher oder RESTIC_AUFBEWAHRUNG=aus (docs/betrieb.md)"
}

# Bei „aus“ wächst die Kopie, bis der getrennte Rechner aufräumt. Größe und Zahl der
# Snapshots nur mit restic selbst ermitteln; nie ein Fehler, höchstens eine WARNUNG.
speicherstand() {
    local json bytes anzahl gb
    json=$(restic stats --mode raw-data --json -q 2>> "$LOG") || json=""
    bytes=$(printf '%s' "$json" | sed -n 's/.*"total_size":\([0-9][0-9]*\).*/\1/p' | head -n 1)
    if [ -z "$bytes" ]; then
        log "HINWEIS: Speicherstand nicht ermittelt (restic stats)"
        return 0
    fi
    anzahl=$(restic snapshots --json -q 2>> "$LOG" | grep -o '"id":"[0-9a-f]*"' | wc -l)
    gb=$(awk -v b="$bytes" 'BEGIN { printf "%.1f", b / 1e9 }')
    log "Speicherstand: $gb GB in $anzahl Snapshots (Aufbewahrung am Server aus)"
    if [ -n "$WARNGRENZE_GB" ] && awk -v b="$bytes" -v g="$WARNGRENZE_GB" 'BEGIN { exit !(g + 0 > 0 && b > g * 1e9) }'; then
        log "WARNUNG: Kopie größer als RESTIC_WARNGRENZE_GB=$WARNGRENZE_GB ($gb GB); „aufbewahrung“ auf dem getrennten Rechner ausführen oder Speicher erweitern"
    fi
    return 0
}

# forget/prune und check; von einem getrennten Rechner mit eigenem Zugang aufrufen
aufbewahrung() {
    exec 9>"$SPERRE"
    flock -n 9 || { echo "läuft bereits"; exit 1; }
    REP=/dev/stdout
    log "=== Start Aufbewahrung (forget/prune)"
    vergessen || exit 1
    restic check >> "$LOG" 2>&1 && log "check ok" || { log "FEHLER: check"; exit 1; }
    log "=== Ende Aufbewahrung"
}

sichern() {
    exec 9>"$SPERRE"
    flock -n 9 || { echo "$(date -Is) läuft bereits" >> "$LOG"; exit 1; }
    REP=$(mktemp)
    FEHLER=0
    log "=== Start HUBIplan-Sicherung"
    # Ist das heutige HUBIplan-Backup da? Sonst trotzdem kopieren, aber melden
    if [ "$(cat "$BACKUPS/.last-run" 2>/dev/null)" != "$(TZ=Europe/Berlin date +%F)" ]; then
        log "WARNUNG: HUBIplan-Backup von heute fehlt (siehe $BACKUPS/backup.log)"
        FEHLER=1
    fi
    # D-M02: .env vor dem restic-Upload mit dem öffentlichen age-Schlüssel verschlüsseln,
    # wenn BACKUP_PUBLIC_KEY gesetzt und age verfügbar ist (so enthält das restic-Repo
    # selbst ohne age-Privatschlüssel keine Klartext-Passwörter aus .env).
    ENV_BACKUP="$ENVDATEI"
    ENV_TMP=""
    AGE_PUB=$(grep '^BACKUP_PUBLIC_KEY=' "$ENVDATEI" 2>/dev/null | tail -n1 | cut -d= -f2- | tr -d '\r"'\''' || true)
    if [ -n "$AGE_PUB" ] && [[ "$AGE_PUB" =~ ^age1[0-9a-z]+$ ]] && command -v age >/dev/null 2>&1; then
        ENV_TMP=$(mktemp -d)
        chmod 700 "$ENV_TMP"
        if age -r "$AGE_PUB" -o "$ENV_TMP/hubiplan.env.age" "$ENVDATEI" 2>>"$LOG"; then
            ENV_BACKUP="$ENV_TMP/hubiplan.env.age"
        else
            log "WARNUNG: .env konnte nicht mit age verschlüsselt werden, sichere unverschlüsselt im restic-Repo"
            rm -rf "$ENV_TMP"
            ENV_TMP=""
        fi
    fi
    nice -n 10 ionice -c3 restic backup --host "$(hostname -f)" --tag hubiplan -q \
        "$BACKUPS" "$ENV_BACKUP" >> "$LOG" 2>&1 \
        && log "restic backup ok" || { log "FEHLER: restic backup (Exit $?)"; FEHLER=1; }
    [ -n "$ENV_TMP" ] && rm -rf "$ENV_TMP"
    # Mail: eigener Snapshot mit Tag „mail“, damit Rücksicherung und Probe der
    # HUBIplan-Sicherungen unverändert bleiben
    MAIL=()
    if [ -e "$MAILPFADE" ]; then
        mapfile -t MAIL < <(mailpfade)
        for p in "${MAIL[@]}"; do
            [ -e "$p" ] || { log "FEHLER: Mailpfad $p fehlt"; FEHLER=1; }
        done
        if [ "${#MAIL[@]}" = 0 ]; then
            log "FEHLER: $MAILPFADE ist leer"; FEHLER=1
        else
            nice -n 10 ionice -c3 restic backup --host "$(hostname -f)" --tag mail -q \
                "${MAIL[@]}" >> "$LOG" 2>&1 \
                && log "restic backup Mail ok (Postfächer: $(du -sh "${MAIL[0]}" 2>/dev/null | cut -f1))" \
                || { log "FEHLER: restic backup Mail (Exit $?)"; FEHLER=1; }
        fi
    fi
    case "$AUFBEWAHRUNG" in
        an) vergessen || FEHLER=1; hinweis_loeschend ;;
        aus) speicherstand ;;
        # Unbekannter Wert: lieber nichts löschen, aber melden
        *) log "FEHLER: RESTIC_AUFBEWAHRUNG=$AUFBEWAHRUNG (an oder aus)"; FEHLER=1 ;;
    esac
    if [ "$(date +%d)" = "01" ]; then
        restic check --read-data-subset=10% >> "$LOG" 2>&1 \
            && log "check ok" || { log "FEHLER: check"; FEHLER=1; }
        probe || FEHLER=1
        [ "${#MAIL[@]}" -gt 0 ] && { probe_mail || FEHLER=1; }
    fi
    touch "$STAND/hubiplan-restic.last-run"
    [ $FEHLER = 0 ] && touch "$STAND/hubiplan-restic.last-ok"
    log "=== Ende (Fehler: $FEHLER)"
    # Mail nur bei Fehlern und am Monatsersten, damit das Postfach ruhig bleibt
    if [ $FEHLER != 0 ] || [ "$(date +%d)" = "01" ]; then
        S="HUBIplan-Sicherung $( [ $FEHLER = 0 ] && echo OK || echo FEHLER ) $(hostname -s) $(date +%F)"
        mail -s "$S" "$MAILTO" < "$REP" || true
    fi
    rm -f "$REP"
    return $FEHLER
}

case "${1:-}" in
    einrichten) einrichten ;;
    aufbewahrung) aufbewahrung ;;
    "") sichern; exit $? ;;
    *) echo "Aufruf: $0 [einrichten|aufbewahrung]"; exit 2 ;;
esac
