#!/bin/bash
# Zweiter Backup-Ort (Gesamtaudit 15.11., OPS-06) ohne Server, Netz oder Container prüfen:
# rsync- und restic-Aufrufe laufen gegen Ersatzbefehle, die nur ihre Argumente aufschreiben.
#   - rsync: --delete wie bisher, nie mit BACKUP_REMOTE_ANHAENGEND=1; Hinweis höchstens
#     einmal am Tag und ohne FEHLER
#   - restic: Standard ruft forget/prune auf (mit Hinweis), RESTIC_AUFBEWAHRUNG=aus nie;
#     Speicherstand und Warngrenze ändern weder Rückgabewert noch last-ok
# Aufruf: scripts/pruefe-zweitort.sh <Wurzel des geprüften Stands>
set -euo pipefail
ROOT="$1"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
fail() { echo "Zweitort: $*" >&2; exit 1; }

sh -n "$ROOT/deploy/backup/zweitort.sh"
sh -n "$ROOT/deploy/backup/backup.sh"
bash -n "$ROOT/deploy/hestia/hubiplan-restic-backup.sh"
grep -q 'zweitort_kopieren "\$DIR" "\$BACKUP_REMOTE" "\$DELETE"' "$ROOT/deploy/backup/backup.sh" \
    || fail "backup.sh nutzt zweitort_kopieren nicht"
if grep -q '^[[:space:]]*rsync ' "$ROOT/deploy/backup/backup.sh"; then
    fail "backup.sh ruft rsync an zweitort.sh vorbei auf"
fi

# --- rsync -------------------------------------------------------------------------
mkdir -p "$T/rbin" "$T/sich"
cat > "$T/rbin/rsync" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "$AUFRUFE"
EOF
chmod +x "$T/rbin/rsync"
rsync_lauf() { # $1 Löschoption, Rest: Umgebung
    local loeschen=$1; shift
    : > "$T/rsync.aufrufe"
    env "$@" AUFRUFE="$T/rsync.aufrufe" PATH="$T/rbin:$PATH" sh -c \
        '. "$1"; zweitort_kopieren "$2" ziel.example.org: "$3" "ssh -o BatchMode=yes"' \
        sh "$ROOT/deploy/backup/zweitort.sh" "$T/sich" "$loeschen"
}
hinweise() { { cat "$T/sich/backup.log" 2>/dev/null || true; } | grep -c 'HINWEIS: Zweiter Ort' || true; }

# Standard (D-M02): anhängend (kein --delete), kein Hinweis
rsync_lauf --delete
if grep -q -- '--delete' "$T/rsync.aufrufe"; then fail "Standard mit --delete statt anhängend"; fi
grep -q -- '^-a -e ssh' "$T/rsync.aufrufe" || fail "Standard: rsync nicht aufgerufen"
grep -q -- "--exclude=\* $T/sich/ ziel.example.org:\$" "$T/rsync.aufrufe" || fail "Quelle/Ziel falsch"
[ "$(hinweise)" = 0 ] || fail "Hinweis im sicheren Standard"

# Ausdrückliches BACKUP_REMOTE_ANHAENGEND=0 erlaubt --delete mit Hinweis (höchstens 1x/Tag)
rsync_lauf --delete BACKUP_REMOTE_ANHAENGEND=0
grep -q -- '^-a --delete -e ssh' "$T/rsync.aufrufe" || fail "ANHAENGEND=0 ohne --delete"
[ "$(hinweise)" = 1 ] || fail "kein Hinweis bei --delete"
rsync_lauf --delete BACKUP_REMOTE_ANHAENGEND=0
[ "$(hinweise)" = 1 ] || fail "Hinweis öfter als einmal am Tag"
if grep -q FEHLER "$T/sich/backup.log"; then fail "Hinweis enthält FEHLER (run.sh-Status)"; fi
[ ! -e "$T/sich/.zweitort-hinweis" ] || [ "$(cat "$T/sich/.zweitort-hinweis")" = "$(date +%F)" ] \
    || fail "Merker falsch"

rm -f "$T/sich/backup.log" "$T/sich/.zweitort-hinweis"
rsync_lauf --delete BACKUP_REMOTE_ANHAENGEND=1
if grep -q -- '--delete' "$T/rsync.aufrufe"; then fail "--delete trotz BACKUP_REMOTE_ANHAENGEND=1"; fi
grep -q -- '^-a -e ssh' "$T/rsync.aufrufe" || fail "anhängend: rsync nicht aufgerufen"
[ "$(hinweise)" = 0 ] || fail "Hinweis trotz anhängend"
# Unvollständiges Backup: backup.sh gibt keine Löschoption vor, dann auch kein Hinweis
rsync_lauf "" BACKUP_REMOTE_ANHAENGEND=0
if grep -q -- '--delete' "$T/rsync.aufrufe"; then fail "--delete ohne Vorgabe"; fi
[ "$(hinweise)" = 0 ] || fail "Hinweis ohne --delete"
# Scheitert rsync, scheitert auch die Kopie
printf '#!/bin/sh\nexit 23\n' > "$T/rbin/rsync"
if rsync_lauf --delete BACKUP_REMOTE_ANHAENGEND=1; then fail "rsync-Fehler verschluckt"; fi
echo "Zweitort: rsync standardmäßig anhängend, --delete nur mit BACKUP_REMOTE_ANHAENGEND=0"

# --- restic ------------------------------------------------------------------------
W="$T/w"
neu_wurzel() {
    rm -rf "$W"
    mkdir -p "$W/bin" "$W/root/.config/restic" "$W/var/log" "$W/var/lib" "$W/run" \
        "$W/opt/hubiplan-backups" "$W/opt/hubiplan" "$W/etc/cron.d"
    echo nur-test > "$W/root/.config/restic/hubiplan.pass"
    echo "TEST=1" > "$W/opt/hubiplan/.env"
    TZ=Europe/Berlin date +%F > "$W/opt/hubiplan-backups/.last-run"
    echo daten > "$W/opt/hubiplan-backups/db_2026-11-01_031500.sql.gz.age"
    echo pruef > "$W/opt/hubiplan-backups/db_2026-11-01_031500.sql.gz.age.hmac"
    echo liste > "$W/opt/hubiplan-backups/dateien_2026-11-01_031500.sha256.age"
    cat > "$W/bin/restic" <<'EOF'
#!/bin/bash
printf '%s\n' "$*" >> "$HUBIPLAN_RESTIC_TESTWURZEL/restic.aufrufe"
case "$1" in
    stats) printf '{"total_size":%s,"total_file_count":3,"snapshots_count":2}\n' "${FAKE_GROESSE:-2500000000}" ;;
    snapshots) printf '[{"time":"x","id":"%064d","short_id":"0"},{"time":"y","id":"%064d","short_id":"1"}]\n' 1 2 ;;
    restore)
        ziel=""; incl=()
        while [ $# -gt 0 ]; do
            case "$1" in --target) ziel=$2; shift ;; --include) incl+=("$2"); shift ;; esac
            shift
        done
        for muster in "${incl[@]}"; do
            for f in $muster; do
                [ -e "$f" ] && mkdir -p "$ziel$(dirname "$f")" && cp "$f" "$ziel$f"
            done
        done ;;
esac
exit 0
EOF
    # Monatserster nach Wunsch (FAKE_TAG), sonst echtes date
    cat > "$W/bin/date" <<'EOF'
#!/bin/sh
if [ "${1:-}" = "+%d" ] && [ -n "${FAKE_TAG:-}" ]; then echo "$FAKE_TAG"; exit 0; fi
exec /bin/date "$@"
EOF
    printf '#!/bin/sh\nshift\nexec "$@"\n' > "$W/bin/ionice"
    printf '#!/bin/sh\necho test.example.org\n' > "$W/bin/hostname"
    printf '#!/bin/sh\n{ echo "BETREFF: $2"; cat; } >> "$HUBIPLAN_RESTIC_TESTWURZEL/mail.aus"\n' > "$W/bin/mail"
    chmod +x "$W/bin/"*
}
restic_lauf() { # Rückgabewert des Skripts; Umgebung als Argumente
    env HUBIPLAN_RESTIC_TESTWURZEL="$W" MAILTO=test@example.org "$@" \
        bash "$ROOT/deploy/hestia/hubiplan-restic-backup.sh" ${ARG:-}
}
konf() { printf '%s\n' "$@" > "$W/root/.config/restic/hubiplan.conf"; }
LOGD="$W/var/log/hubiplan-restic.log"

# Standard (D-M02): wie „aus“, nie forget/prune am Server, dafür Speicherstand
neu_wurzel
restic_lauf FAKE_TAG=15 || fail "Standard: Rückgabewert $?"
if grep -Eq '^(forget|prune)' "$W/restic.aufrufe"; then fail "Standard ruft forget/prune auf"; fi
grep -q '^stats' "$W/restic.aufrufe" || fail "Standard fragt Speicherstand nicht ab"
[ -e "$W/var/lib/hubiplan-restic.last-ok" ] || fail "Standard: last-ok fehlt"
grep -q '=== Ende (Fehler: 0)' "$LOGD" || fail "Standard: Fehler gemeldet"
[ ! -e "$W/mail.aus" ] || fail "Standard: Mail ohne Anlass"

# Ausdrücklich „an“: forget/prune auf dem Server mit täglichem Hinweis (kein Fehler)
neu_wurzel
konf RESTIC_AUFBEWAHRUNG=an
restic_lauf FAKE_TAG=15 || fail "an: Rückgabewert $?"
grep -q '^forget .*--prune' "$W/restic.aufrufe" || fail "an: ohne forget/prune"
[ "$(grep -c 'HINWEIS: forget/prune läuft' "$LOGD")" = 1 ] || fail "an: Hinweis fehlt"
rm "$W/var/lib/hubiplan-restic.last-ok"
restic_lauf FAKE_TAG=15 || fail "an (2. Lauf): Rückgabewert $?"
[ "$(grep -c 'HINWEIS: forget/prune läuft' "$LOGD")" = 1 ] || fail "Hinweis öfter als einmal am Tag"
[ -e "$W/var/lib/hubiplan-restic.last-ok" ] || fail "an (2. Lauf): last-ok fehlt"

# „aus“: nie forget/prune, dafür Speicherstand; Monatserster mit check, Probe und Mail
neu_wurzel
konf RESTIC_AUFBEWAHRUNG=aus
restic_lauf FAKE_TAG=01 || fail "aus: Rückgabewert $?"
if grep -Eq '^(forget|prune)' "$W/restic.aufrufe"; then fail "aus: forget/prune aufgerufen"; fi
grep -q '^backup ' "$W/restic.aufrufe" || fail "aus: keine Sicherung"
grep -q '^check ' "$W/restic.aufrufe" || fail "aus: kein check am Monatsersten"
grep -q 'Probe ok' "$LOGD" || fail "aus: Probe nicht ok"
grep -q 'Speicherstand: 2.5 GB in 2 Snapshots' "$LOGD" || fail "aus: Speicherstand fehlt"
if grep -q 'HINWEIS: forget/prune' "$LOGD"; then fail "aus: Lösch-Hinweis"; fi
if grep -q 'WARNUNG' "$LOGD"; then fail "aus: Warnung ohne Grenze"; fi
[ -e "$W/var/lib/hubiplan-restic.last-ok" ] || fail "aus: last-ok fehlt"
grep -q 'BETREFF: HUBIplan-Sicherung OK' "$W/mail.aus" || fail "aus: Monatsmail fehlt/nicht OK"
grep -q 'Speicherstand: 2.5 GB' "$W/mail.aus" || fail "aus: Speicherstand nicht in der Monatsmail"

# Warngrenze überschritten: WARNUNG im Protokoll und in der Monatsmail, aber kein Fehler
neu_wurzel
konf RESTIC_AUFBEWAHRUNG=aus RESTIC_WARNGRENZE_GB=1
restic_lauf FAKE_TAG=01 FAKE_GROESSE=5000000000 || fail "Warngrenze: Rückgabewert $?"
grep -q 'WARNUNG: Kopie größer als RESTIC_WARNGRENZE_GB=1 (5.0 GB)' "$LOGD" || fail "Warngrenze: keine Warnung"
[ -e "$W/var/lib/hubiplan-restic.last-ok" ] || fail "Warngrenze: last-ok fehlt"
grep -q '=== Ende (Fehler: 0)' "$LOGD" || fail "Warngrenze: als Fehler gezählt"
grep -q 'BETREFF: HUBIplan-Sicherung OK' "$W/mail.aus" || fail "Warngrenze: Mailbetreff nicht OK"
grep -q 'WARNUNG: Kopie größer' "$W/mail.aus" || fail "Warngrenze: nicht in der Monatsmail"
# Unter der Grenze keine Warnung
neu_wurzel
konf RESTIC_AUFBEWAHRUNG=aus RESTIC_WARNGRENZE_GB=10
restic_lauf FAKE_TAG=15 FAKE_GROESSE=5000000000 || fail "unter Grenze: Rückgabewert $?"
if grep -q 'WARNUNG' "$LOGD"; then fail "unter Grenze: Warnung"; fi

# Speicherstand nicht ermittelbar: nur Hinweis, kein Fehler
neu_wurzel
konf RESTIC_AUFBEWAHRUNG=aus
restic_lauf FAKE_TAG=15 FAKE_GROESSE=null || fail "stats kaputt: Rückgabewert $?"
grep -q 'HINWEIS: Speicherstand nicht ermittelt' "$LOGD" || fail "stats kaputt: kein Hinweis"
[ -e "$W/var/lib/hubiplan-restic.last-ok" ] || fail "stats kaputt: last-ok fehlt"

# Unbekannter Wert: nichts löschen, aber als Fehler melden
neu_wurzel
konf RESTIC_AUFBEWAHRUNG=vielleicht
if restic_lauf FAKE_TAG=15; then fail "unbekannter Wert ohne Fehler"; fi
if grep -Eq '^(forget|prune)' "$W/restic.aufrufe"; then fail "unbekannter Wert: forget aufgerufen"; fi
[ ! -e "$W/var/lib/hubiplan-restic.last-ok" ] || fail "unbekannter Wert: last-ok gesetzt"

# „aufbewahrung“ (getrennter Rechner): forget/prune und check, sonst nichts
neu_wurzel
konf RESTIC_AUFBEWAHRUNG=aus
ARG=aufbewahrung restic_lauf > "$T/aufbewahrung.aus" || fail "aufbewahrung: Rückgabewert $?"
grep -q '^forget .*--keep-daily 14 .*--prune' "$W/restic.aufrufe" || fail "aufbewahrung: kein forget/prune"
grep -q '^check' "$W/restic.aufrufe" || fail "aufbewahrung: kein check"
if grep -q '^backup' "$W/restic.aufrufe"; then fail "aufbewahrung: sichert"; fi
grep -q 'Aufbewahrung/prune ok' "$T/aufbewahrung.aus" || fail "aufbewahrung: keine Ausgabe"
echo "Zweitort: restic forget/prune nur im Standard oder mit „aufbewahrung“, Speicherstand ohne Alarm"
