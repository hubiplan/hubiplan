#!/bin/sh
# Verschlüsseltes Backup der Datenbank und der Dateien (Logos, Importe/Exporte).
#
# Mit BACKUP_PUBLIC_KEY (age-Empfänger, age1…) verschlüsselt der Server nur mit dem
# öffentlichen Schlüssel. Entschlüsseln kann nur, wer den privaten Schlüssel hat; der
# liegt nicht auf dem Server. Der Rücksicherungstest läuft dann vor dem Verschlüsseln
# auf dem Klartext im Arbeitsspeicher (tmpfs).
#   Entschlüsseln: age -d -i hubiplan-backup.key DATEI.age
# Ohne BACKUP_PUBLIC_KEY (alte Form): Passphrase aus der .env; der Rücksicherungstest
# läuft nach dem Verschlüsseln, aber vor dem Aufräumen alter Backups und der Kopie.
#   Entschlüsseln: openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE -in DATEI
# Zu jeder Datei gehört DATEI.hmac (HMAC-SHA256 mit BACKUP_HMAC_KEY); vor dem
# Einspielen mit verify.sh prüfen.
# Zu den Dateien gehört dateien_STAMP.sha256.(age|enc): die Liste aller gesicherten
# Dateien mit SHA-256, im selben Moment wie das Archiv erstellt. Der Rücksicherungstest
# prüft damit, ob jede Datei, auf die die Datenbank zeigt, im Backup steht.
#   Nach dem Auspacken prüfen: cd ZIEL && sha256sum -c dateien_STAMP.sha256
set -eu
# Ein Fehler irgendwo in der Kette (z. B. abgebrochenes pg_dump) bricht ab, statt dass
# eine unvollständige Datei als Backup gilt
set -o pipefail
: "${BACKUP_HMAC_KEY:?BACKUP_HMAC_KEY fehlt}"

DIR="${BACKUP_DIR:-/backups}"
DATA_KEY_FILE="${BACKUP_DATA_KEY_FILE:-/run/secrets/datenschluessel}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"
STAMP="$(date +%Y-%m-%d_%H%M%S)_$(openssl rand -hex 6)"
ENC="openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:BACKUP_PASSPHRASE"
DEC="openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE"

# Zweiter Ort: Schlüssel und bekannter Rechnerschlüssel aus /run/backup-ssh (schreibgeschützt
# eingebunden, siehe docker-compose.server.yml). Fehlt etwas, bricht das Backup ab, bevor
# alte Sicherungen aufgeräumt werden (Gesamtaudit 30.10., I-F02).
SSH_DIR="${BACKUP_SSH_MOUNT:-/run/backup-ssh}"
SSH_KEY="$SSH_DIR/id_ed25519"
[ -r "$SSH_KEY" ] || SSH_KEY=/run/secrets/backup_ssh_key  # alte Ablage

mkdir -p "$DIR"
umask 077
RECEIPT_NAME=${BACKUP_RECEIPT_NAME:-}
case "$RECEIPT_NAME" in *[!a-zA-Z0-9_-]*) echo "Ungültiger Backup-Nachweisname" >&2; exit 1;; esac
# Per destination: concurrent/manual starts may not overwrite markers or clean
# another run's temporary files. flock is released automatically even on crash.
exec 9> "$DIR/.backup.lock"
flock -n 9 || { echo "Backup läuft bereits; dieser Lauf wurde nicht gestartet." >&2; exit 1; }
# Klartext nur im Arbeitsspeicher (tmpfs), nie im Backup-Ordner
WORK=$(mktemp -d "${BACKUP_WORK:-/tmp}/backup.XXXXXX")
# Halbfertige Dateien und Klartext nie liegen lassen
trap 'rm -f "$DIR"/*.enc.tmp "$DIR"/*.age.tmp "$DIR"/*.hmac.tmp "$DIR"/*.sha256.tmp; rm -rf "$WORK"' EXIT

fail() {
    echo "$(date '+%F %T') FEHLER: $1" >> "$DIR/backup.log"
    echo "$1" >&2
    exit 1
}

# Prüfsumme schreiben, dann die fertige Datei an ihren Platz
sign() {
    hmac.sh "$1.tmp" > "$1.hmac.tmp" || fail "Prüfsumme für $(basename "$1") fehlgeschlagen"
    mv "$1.hmac.tmp" "$1.hmac"
    mv "$1.tmp" "$1"
}

# Dateiliste mit Prüfsummen, direkt vor dem Archiv (Datenbank und Dateien entstehen
# nacheinander; die Liste zeigt, welche Dateien genau im Archiv stehen)
file_list() {
    (cd /data && find . -type f -exec sha256sum {} + | sort -k 2) > "$WORK/dateien.sha256" \
        || fail "Dateiliste ist fehlgeschlagen ($STAMP)"
}

# Datenbank (PGHOST, PGUSER, PGPASSWORD, PGDATABASE kommen aus der Umgebung)
if [ -n "${BACKUP_PUBLIC_KEY:-}" ]; then
    AGE="age -r $BACKUP_PUBLIC_KEY"
    pg_dump --no-owner --no-privileges | gzip -9 > "$WORK/db.sql.gz" \
        || fail "pg_dump ist fehlgeschlagen, kein Backup $STAMP"
    # Vollständig? pg_dump schreibt am Ende eine feste Schlusszeile.
    gunzip -c "$WORK/db.sql.gz" | tail -n 5 | grep -c "PostgreSQL database dump complete" > /dev/null \
        || fail "Datenbank-Backup $STAMP ist unvollständig"
    # Dateien vor dem Rücksicherungstest, damit er die Dateiliste prüfen kann.
    # Fertig (signiert) werden sie erst, wenn der Test bestanden ist.
    LIST=""
    if [ -d /data ]; then
        file_list
        LIST="$WORK/dateien.sha256"
        tar -C /data -czf - . | archive-check.py "$LIST" --copy | $AGE -o "$DIR/files_$STAMP.tar.gz.age.tmp" \
            || fail "Sicherung der Dateien ist fehlgeschlagen ($STAMP)"
        $AGE -o "$DIR/dateien_$STAMP.sha256.age.tmp" "$LIST" \
            || fail "Verschlüsseln der Dateiliste fehlgeschlagen ($STAMP)"
    fi
    # Rücksicherungstest jetzt, denn danach kann der Server die Datei nicht mehr lesen
    restore-test.sh --klartext "$WORK/db.sql.gz" "db_$STAMP.sql.gz.age" $LIST \
        || fail "Rücksicherungstest für $STAMP fehlgeschlagen"
    $AGE -o "$DIR/db_$STAMP.sql.gz.age.tmp" "$WORK/db.sql.gz" \
        || fail "Verschlüsseln des Datenbank-Backups fehlgeschlagen ($STAMP)"
    rm -f "$WORK/db.sql.gz"
    sign "$DIR/db_$STAMP.sql.gz.age"
    LATEST_DB="$DIR/db_$STAMP.sql.gz.age"
    if [ -n "$LIST" ]; then
        sign "$DIR/files_$STAMP.tar.gz.age"
        sign "$DIR/dateien_$STAMP.sha256.age"
    fi
else
    pg_dump --no-owner --no-privileges | gzip -9 | $ENC -out "$DIR/db_$STAMP.sql.gz.enc.tmp" \
        || fail "pg_dump ist fehlgeschlagen, kein Backup $STAMP"
    # Vollständig? pg_dump schreibt am Ende eine feste Schlusszeile.
    $DEC -in "$DIR/db_$STAMP.sql.gz.enc.tmp" | gunzip | tail -n 5 \
        | grep -c "PostgreSQL database dump complete" > /dev/null \
        || fail "Datenbank-Backup $STAMP ist unvollständig"
    sign "$DIR/db_$STAMP.sql.gz.enc"
    LATEST_DB="$DIR/db_$STAMP.sql.gz.enc"
    if [ -d /data ]; then
        file_list
        tar -C /data -czf - . | archive-check.py "$WORK/dateien.sha256" --copy | $ENC -out "$DIR/files_$STAMP.tar.gz.enc.tmp" \
            || fail "Sicherung der Dateien ist fehlgeschlagen ($STAMP)"
        $ENC -in "$WORK/dateien.sha256" -out "$DIR/dateien_$STAMP.sha256.enc.tmp" \
            || fail "Verschlüsseln der Dateiliste fehlgeschlagen ($STAMP)"
        sign "$DIR/files_$STAMP.tar.gz.enc"
        sign "$DIR/dateien_$STAMP.sha256.enc"
    fi
    # Rücksicherungstest vor dem Aufräumen und vor der Kopie: Ein Backup, das sich
    # nicht einspielen lässt, verdrängt weder alte Backups noch die Kopie (Audit I-F01)
    restore-test.sh > /dev/null || fail "Rücksicherungstest für $STAMP fehlgeschlagen"
fi

# Löschliste (nur Kennungen, keine Namen) neben die Backups legen: Nach dem Einspielen
# eines Backups auf einem neuen Server gehört sie ins Volume loeschliste (docs/betrieb.md)
if [ -f /loeschliste/loeschliste.jsonl ]; then
    cp /loeschliste/loeschliste.jsonl "$DIR/loeschliste.jsonl.tmp" \
        && mv "$DIR/loeschliste.jsonl.tmp" "$DIR/loeschliste.jsonl" \
        || fail "Löschliste konnte nicht kopiert werden ($STAMP)"
fi

# Hauptschlüssel der Datenverschlüsselung (Docker-Secret) verschlüsselt neben die Backups:
# Ohne ihn sind verschlüsselte Dateien und Felder in den Backups nicht lesbar. Mit
# BACKUP_PUBLIC_KEY kann die Kopie nur lesen, wer den privaten Backup-Schlüssel hat
# (docs/betrieb.md, Abschnitt Verschlüsselung); sonst wie die Backups mit der Passphrase.
# Fehlt die Kopie, gilt das Backup als unvollständig: Alarm, alte Backups bleiben
# (Audit 02.11. O-F01).
key_incomplete() {
    echo "$(date '+%F %T') WARNUNG: $1 ($STAMP)" >> "$DIR/backup.log"
    echo "$1" >> "$DIR/.unvollstaendig"
}
# One immutable tmpfs copy is the source of both encryption and fingerprint.
# Atomic replacement of the live file after cp must not create a mixed pair.
KEY_SNAPSHOT="$WORK/datenschluessel"
if [ ! -r "$DATA_KEY_FILE" ] || ! cp "$DATA_KEY_FILE" "$KEY_SNAPSHOT"; then
    key_incomplete "Hauptschlüssel nicht lesbar, keine Schlüsselkopie beim Backup"
else
    if [ "${BACKUP_REQUIRE_COMPLETE:-0}" = 1 ]; then
        if ! python3 - "$KEY_SNAPSHOT" <<'PYKEY'
import base64
import pathlib
import sys
try:
    lines = pathlib.Path(sys.argv[1]).read_text(encoding="ascii").splitlines()
    keys = [v.strip() for v in lines if v.strip() and not v.lstrip().startswith("#")]
    assert keys
    for key in keys:
        assert len(base64.b64decode(key + "=" * (-len(key) % 4), altchars=b"-_", validate=True)) == 32
except (ValueError, AssertionError, OSError):
    sys.exit(1)
PYKEY
        then
            key_incomplete "Hauptschlüssel-Kopie hat kein gültiges Schlüsselformat"
        fi
    fi
    if [ -n "${BACKUP_PUBLIC_KEY:-}" ]; then
        age -r "$BACKUP_PUBLIC_KEY" -o "$DIR/datenschluessel_$STAMP.age.tmp" "$KEY_SNAPSHOT" \
            && [ -s "$DIR/datenschluessel_$STAMP.age.tmp" ] \
            && sign "$DIR/datenschluessel_$STAMP.age" \
            || key_incomplete "Kopie des Hauptschlüssels fehlgeschlagen"
    else
        $ENC -in "$KEY_SNAPSHOT" -out "$DIR/datenschluessel_$STAMP.enc.tmp" \
            && [ -s "$DIR/datenschluessel_$STAMP.enc.tmp" ] \
            && sign "$DIR/datenschluessel_$STAMP.enc" \
            || key_incomplete "Kopie des Hauptschlüssels fehlgeschlagen"
    fi
    sha256sum "$KEY_SNAPSHOT" | cut -d ' ' -f 1 > "$DIR/datenschluessel_$STAMP.sha256.tmp"
    sign "$DIR/datenschluessel_$STAMP.sha256"
    # One-release compatibility aliases are never used by a strict set restore.
    if [ -n "${BACKUP_PUBLIC_KEY:-}" ]; then KEY_EXT=age; else KEY_EXT=enc; fi
    for suffix in "$KEY_EXT" "$KEY_EXT.hmac" sha256 sha256.hmac; do
        cp "$DIR/datenschluessel_$STAMP.$suffix" "$DIR/datenschluessel.$suffix.tmp" \
            && mv "$DIR/datenschluessel.$suffix.tmp" "$DIR/datenschluessel.$suffix" \
            || key_incomplete "Letzte Schlüsselkopie konnte nicht bereitgestellt werden"
    done
fi

# Kettenköpfe des Änderungsprotokolls (nur Nummer und Prüfsumme je Organisation, keine
# Inhalte) unverschlüsselt anhängen. Die Datei wandert mit restic nach Hetzner; ältere
# Stände bleiben dort in den Schnappschüssen. Abgleich: manage.py kettenkoepfe_pruefen
# (FQ-17, Ralf 01.11.2026). Ein Fehler hier stoppt das Backup nicht, steht aber im Log.
if psql -At -F ' ' -c "SELECT '$STAMP', organization_id, head_seq, head_hash
        FROM audit_auditcheck WHERE head_seq IS NOT NULL AND head_hash <> ''
        ORDER BY organization_id" > "$WORK/kettenkoepfe" 2>/dev/null; then
    cat "$WORK/kettenkoepfe" >> "$DIR/kettenkoepfe.log"
    chmod 644 "$DIR/kettenkoepfe.log"
else
    echo "$(date '+%F %T') WARNUNG: Kettenköpfe nicht geschrieben ($STAMP)" >> "$DIR/backup.log"
fi

if [ -n "${BACKUP_REMOTE:-}" ]; then
    [ -r "$SSH_KEY" ] || fail "Zweiter Ort: SSH-Schlüssel fehlt ($SSH_DIR/id_ed25519)"
    [ -r "$SSH_DIR/known_hosts" ] || fail "Zweiter Ort: $SSH_DIR/known_hosts fehlt"
fi

# Unvollständiges Backup (Dateien fehlen): ältere, vollständige Backups nicht löschen und
# am zweiten Ort nichts entfernen (Gesamtaudit 31.10.b, INF-F03)
DELETE="--delete"
if [ -f "$DIR/.unvollstaendig" ]; then
    [ "${BACKUP_REQUIRE_COMPLETE:-0}" != 1 ] || fail "Vollständiges Backup erforderlich ($STAMP)"
    echo "$(date '+%F %T') WARNUNG: Backup $STAMP unvollständig, alte Backups bleiben" >> "$DIR/backup.log"
    DELETE=""
elif [ "${BACKUP_PRESERVE_EXISTING:-0}" = 1 ]; then
    DELETE=""
else
    # Alte Backups entfernen
    # Die Schlüsselkopie bleibt immer (sie wird täglich erneuert)
    find "$DIR" -maxdepth 1 \( -name '*.enc' -o -name '*.enc.hmac' -o -name '*.age' -o -name '*.age.hmac' -o -name 'datenschluessel_*.sha256' -o -name 'datenschluessel_*.sha256.hmac' \) \
        ! -name 'datenschluessel.*' -mtime +"$KEEP_DAYS" -delete
fi

# Optional: Kopie an einen zweiten Ort (z. B. user@host:/pfad, per SSH-Schlüssel)
if [ -n "${BACKUP_REMOTE:-}" ]; then
    # Fester Rechnerschlüssel (known_hosts), kein „beim ersten Mal vertrauen“
    # shellcheck disable=SC2086
    rsync -a $DELETE \
        -e "ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$SSH_DIR/known_hosts -i $SSH_KEY" \
        --include='*.enc' --include='*.enc.hmac' --include='*.age' --include='*.age.hmac' \
        --include='datenschluessel_*.sha256' --include='datenschluessel_*.sha256.hmac' \
        --include='datenschluessel.sha256' --include='datenschluessel.sha256.hmac' \
        --include='*.receipt' --include='*.receipt.hmac' \
        --include='restore-test.log' --include='loeschliste.jsonl' --include='kettenkoepfe.log' --exclude='*' "$DIR/" "$BACKUP_REMOTE" \
        || fail "Kopie nach $BACKUP_REMOTE fehlgeschlagen (lokales Backup $STAMP ist ok)"
    echo "$(date '+%F %T') Kopie nach $BACKUP_REMOTE ok" >> "$DIR/backup.log"
fi

echo "$(date '+%F %T') Backup $STAMP ok ($(du -h "$LATEST_DB" | cut -f1))" >> "$DIR/backup.log"

# Nur ein erfolgreicher vollständiger Lauf darf einen satzgebundenen Nachweis
# veröffentlichen. Kein Auswerten von 'neuestes Backup' oder globalen Statusdateien.
if [ -n "$RECEIPT_NAME" ]; then
    [ ! -f "$DIR/.unvollstaendig" ] || fail "Kein Nachweis für unvollständiges Backup"
    printf '%s\n%s\n' "$STAMP" "${KEY_EXT}" > "$DIR/$RECEIPT_NAME.receipt.tmp"
    sign "$DIR/$RECEIPT_NAME.receipt"
fi
