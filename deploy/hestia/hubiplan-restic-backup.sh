#!/bin/bash
# Optionale zweite Backup-Kopie: überträgt verschlüsselte Anwendungssicherungen
# und die .env per restic auf einen getrennten SFTP-Speicher. Zugang und Ziel
# werden je Installation lokal auf dem Server konfiguriert.
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
# Ohne Argument: Sicherung (so ruft cron es täglich auf). Gibt keine Passwörter aus.
set -u
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

export RESTIC_REPOSITORY=${RESTIC_REPOSITORY:-sftp:storagebox:restic-hubiplan}
export RESTIC_CACHE_DIR=/root/.cache/restic
PASSDATEI=/root/.config/restic/hubiplan.pass
export RESTIC_PASSWORD_FILE=$PASSDATEI
# Empfänger der Fehlermeldungen: eine Adresse in MAILDATEI (nur auf dem Server), sonst root
MAILDATEI=/root/.config/restic/hubiplan.mailto
MAILTO=${MAILTO:-$(head -n1 "$MAILDATEI" 2>/dev/null || echo root)}
LOG=/var/log/hubiplan-restic.log
BACKUPS=/opt/hubiplan-backups
ENVDATEI=/opt/hubiplan/.env
CRON=/etc/cron.d/hubiplan-restic
# Zusätzlich zu sichernde Mailpfade, eine Zeile je Pfad; fehlt die Datei, keine Mailsicherung
MAILPFADE=/root/.config/restic/hubiplan.mail

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

sichern() {
    exec 9>/run/hubiplan-restic.lock
    flock -n 9 || { echo "$(date -Is) läuft bereits" >> "$LOG"; exit 1; }
    REP=$(mktemp)
    FEHLER=0
    log "=== Start HUBIplan-Sicherung"
    # Ist das heutige HUBIplan-Backup da? Sonst trotzdem kopieren, aber melden
    if [ "$(cat "$BACKUPS/.last-run" 2>/dev/null)" != "$(TZ=Europe/Berlin date +%F)" ]; then
        log "WARNUNG: HUBIplan-Backup von heute fehlt (siehe $BACKUPS/backup.log)"
        FEHLER=1
    fi
    nice -n 10 ionice -c3 restic backup --host "$(hostname -f)" --tag hubiplan -q \
        "$BACKUPS" "$ENVDATEI" >> "$LOG" 2>&1 \
        && log "restic backup ok" || { log "FEHLER: restic backup (Exit $?)"; FEHLER=1; }
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
    restic forget --tag hubiplan --tag mail --keep-daily 14 --keep-weekly 8 --keep-monthly 12 \
        --group-by host,tags --prune -q >> "$LOG" 2>&1 \
        && log "Aufbewahrung/prune ok" || { log "FEHLER: forget/prune"; FEHLER=1; }
    if [ "$(date +%d)" = "01" ]; then
        restic check --read-data-subset=10% >> "$LOG" 2>&1 \
            && log "check ok" || { log "FEHLER: check"; FEHLER=1; }
        probe || FEHLER=1
        [ "${#MAIL[@]}" -gt 0 ] && { probe_mail || FEHLER=1; }
    fi
    touch /var/lib/hubiplan-restic.last-run
    [ $FEHLER = 0 ] && touch /var/lib/hubiplan-restic.last-ok
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
    "") sichern; exit $? ;;
    *) echo "Aufruf: $0 [einrichten]"; exit 2 ;;
esac
