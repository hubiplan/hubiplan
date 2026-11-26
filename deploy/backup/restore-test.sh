#!/bin/sh
# Rücksicherungstest: ein Datenbank-Backup in eine leere Wegwerf-Datenbank einspielen.
# Die laufende Datenbank bleibt unberührt.
#
#   restore-test.sh                          # neuestes Backup mit Passphrase (alte Form)
#   restore-test.sh --age DUMP IDENTITAET    # ausschließlich isoliert lokal
#   restore-test.sh --passphrase DUMP        # vollständiger lokaler Dateisatz/Schlüssel
#   restore-test.sh --klartext DATEI NAME [DATEILISTE]
#                                            # Klartext-Dump (gzip) vor dem Verschlüsseln
#                                            # mit öffentlichem Schlüssel (siehe backup.sh)
# Gibt es zum Backup eine Dateiliste (dateien_STAMP.sha256), prüft der Test außerdem,
# ob jede Datei, auf die die Datenbank zeigt, darin steht (Felder: dateifelder.txt).
set -eu
set -o pipefail

DIR="${BACKUP_DIR:-/backups}"
AGE_SOURCE=""
FULL_RESTORE=0
if [ "${1:-}" = "--age" ] || [ "${1:-}" = "--legacy-age" ]; then
    [ "${1:-}" = "--age" ] && FULL_RESTORE=1
    AGE_SOURCE="${2:?Explizite age-Dumpdatei fehlt}"
    IDENTITY="${3:?Separat bereitgestellter privater age-Schlüssel fehlt}"
    NAME=$(basename "$AGE_SOURCE")
    case "$NAME" in db_*.sql.gz.age) ;; *) echo "Ungültiger Dumpname" >&2; exit 1;; esac
    DIR=$(dirname "$AGE_SOURCE")
    STAMP=${NAME#db_}; STAMP=${STAMP%.sql.gz.age}
    verify.sh "$AGE_SOURCE"
    read_dump() { age -d -i "$IDENTITY" "$AGE_SOURCE" | gunzip; }
    LIST=""
elif [ "${1:-}" = "--klartext" ]; then
    SOURCE="${2:?Datei fehlt}"
    NAME="${3:-$(basename "$SOURCE")}"
    LIST="${4:-}"
    read_dump() { gunzip -c "$SOURCE"; }
else
    if [ "${1:-}" != "--passphrase" ] && [ "${1:-}" != "--legacy-passphrase" ] && [ -n "${BACKUP_PUBLIC_KEY:-}" ]; then
        echo "Mit BACKUP_PUBLIC_KEY prüft backup.sh die Rücksicherung selbst." >&2
        exit 0
    fi
    if [ "${1:-}" = "--passphrase" ] || [ "${1:-}" = "--legacy-passphrase" ]; then
        [ "${1:-}" = "--passphrase" ] && FULL_RESTORE=1
        SOURCE="${2:?Explizite verschlüsselte Dumpdatei fehlt}"
        DIR=$(dirname "$SOURCE")
    else
        SOURCE=$(ls -1t "$DIR"/db_*.sql.gz.enc | head -1)
    fi
    NAME=$(basename "$SOURCE")
    case "$NAME" in db_*.sql.gz.enc) ;; *) echo "Ungültiger Dumpname" >&2; exit 1;; esac
    # Zuerst die Prüfsumme: eine veränderte Datei wird gar nicht erst entschlüsselt
    verify.sh "$SOURCE"
    read_dump() {
        openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE -in "$SOURCE" \
            | gunzip
    }
    # Dateiliste mit demselben Zeitstempel (db_STAMP.sql.gz.enc -> dateien_STAMP.sha256.enc)
    STAMP=${NAME#db_}
    STAMP=${STAMP%.sql.gz.enc}
    LIST_ENC="$DIR/dateien_$STAMP.sha256.enc"
    LIST=""
fi
TMP=$(mktemp -d)
trap 'pg_ctl -D "$TMP/data" -m immediate stop > /dev/null 2>&1 || true; rm -rf "$TMP"' EXIT

if [ -n "${LIST_ENC:-}" ] && [ -f "$LIST_ENC" ]; then
    verify.sh "$LIST_ENC"
    openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE \
        -in "$LIST_ENC" -out "$TMP/dateien.sha256"
    LIST="$TMP/dateien.sha256"
fi

# Verify decrypted archive bytes, not just names of currently mounted files.
if [ -n "$AGE_SOURCE" ]; then
    LIST="$TMP/dateien.sha256"
    verify.sh "$DIR/dateien_$STAMP.sha256.age"
    verify.sh "$DIR/files_$STAMP.tar.gz.age"
    age -d -i "$IDENTITY" "$DIR/dateien_$STAMP.sha256.age" > "$LIST"
    age -d -i "$IDENTITY" "$DIR/files_$STAMP.tar.gz.age" | archive-check.py "$LIST"
elif [ -n "${LIST_ENC:-}" ] && [ -f "$LIST_ENC" ]; then
    ARCHIVE="$DIR/files_$STAMP.tar.gz.enc"
    verify.sh "$ARCHIVE"
    openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE -in "$ARCHIVE" \
        | archive-check.py "$LIST"
fi

if [ "$FULL_RESTORE" = 1 ]; then
    [ -n "$LIST" ] && [ -f "$LIST" ] || { echo "Missing full recovery file manifest" >&2; exit 1; }
    if [ -n "$AGE_SOURCE" ]; then
        KEY_COPY="$DIR/datenschluessel_$STAMP.age"
        verify.sh "$KEY_COPY"
        age -d -i "$IDENTITY" "$KEY_COPY" > "$TMP/datenschluessel"
    else
        KEY_COPY="$DIR/datenschluessel_$STAMP.enc"
        verify.sh "$KEY_COPY"
        openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE \
            -in "$KEY_COPY" -out "$TMP/datenschluessel"
    fi
    verify.sh "$DIR/datenschluessel_$STAMP.sha256"
    ACTUAL_KEY_HASH=$(sha256sum "$TMP/datenschluessel" | cut -d ' ' -f 1)
    [ "$ACTUAL_KEY_HASH" = "$(cat "$DIR/datenschluessel_$STAMP.sha256")" ] || {
        echo "Recovered data key does not match signed source fingerprint" >&2; exit 1;
    }
    python3 - "$TMP/datenschluessel" <<'PYKEY'
import base64, pathlib, sys
lines = pathlib.Path(sys.argv[1]).read_text(encoding="ascii").splitlines()
keys = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
assert keys, "Empty data key ring"
for key in keys:
    padded = key + "=" * (-len(key) % 4)
    assert len(base64.b64decode(padded, altchars=b"-_", validate=True)) == 32, "Invalid data key"
PYKEY
fi

initdb -D "$TMP/data" -U restoretest --auth=trust --no-locale --encoding=UTF8 > /dev/null
pg_ctl -D "$TMP/data" -o "-c listen_addresses='' -k $TMP" -w start > /dev/null
createdb -h "$TMP" -U restoretest restore

# D-H03: Entschlüsselten Dump zuerst getrennt prüfen (PG-18 \restrict-Rahmung, keine
# ungeschützten psql-Metabefehle wie \! nach \unrestrict) und psql ohne Zugriff auf
# $IDENTITY / $BACKUP_PASSPHRASE ausführen.
DUMP_FILE="$TMP/dump.sql"
umask 077
read_dump > "$DUMP_FILE"
python3 - "$DUMP_FILE" <<'PYDUMP'
import re, sys

path = sys.argv[1]
token = None
seen_unrestrict = False
with open(path, "r", encoding="utf-8", errors="surrogateescape") as fh:
    for lineno, raw in enumerate(fh, 1):
        line = raw.rstrip("\r\n")
        if token is None:
            stripped = line.strip()
            if not stripped or stripped.startswith("--"):
                continue
            m = re.fullmatch(r"\\restrict\s+([A-Za-z0-9]+)", stripped)
            if not m or len(m.group(1)) < 8:
                sys.stderr.write(
                    f"FEHLER: Dump beginnt in Zeile {lineno} nicht mit PG-18 \\restrict-Schutz.\n"
                )
                sys.exit(1)
            token = m.group(1)
            continue
        if seen_unrestrict:
            stripped = line.strip()
            if stripped and not stripped.startswith("--"):
                sys.stderr.write(
                    f"FEHLER: Unerlaubter Inhalt nach \\unrestrict in Zeile {lineno}.\n"
                )
                sys.exit(1)
            continue
        if line.startswith("\\unrestrict"):
            if line.strip() == f"\\unrestrict {token}":
                seen_unrestrict = True
            else:
                sys.stderr.write(
                    f"FEHLER: Ungültiges \\unrestrict in Zeile {lineno}.\n"
                )
                sys.exit(1)

if token is None:
    sys.stderr.write("FEHLER: Dump enthält keinen \\restrict-Schutz.\n")
    sys.exit(1)
PYDUMP

env -i PATH="$PATH" HOME="$TMP" psql -h "$TMP" -U restoretest -d restore -v ON_ERROR_STOP=1 -q \
    < "$DUMP_FILE" > /dev/null
rm -f "$DUMP_FILE"

ORGS=$(psql -h "$TMP" -U restoretest -d restore -tAc "SELECT count(*) FROM organizations_organization")
MEMBERS=$(psql -h "$TMP" -U restoretest -d restore -tAc "SELECT count(*) FROM members_membership")

FILES=""
rm -f "$DIR/.unvollstaendig"
FIELDS="${BACKUP_FILE_FIELDS:-/usr/local/share/hubiplan/dateifelder.txt}"
if [ -n "$LIST" ] && [ -f "$FIELDS" ]; then
    # Verweise aus der Datenbank, als Pfad wie in der Dateiliste (./media/…, ./private/…)
    grep -v '^#' "$FIELDS" | while read -r table column root; do
        [ -n "$table" ] || continue
        psql -h "$TMP" -U restoretest -d restore -tA -v ON_ERROR_STOP=1 -c \
            "SELECT './$root/' || \"$column\" FROM \"$table\" WHERE \"$column\" <> ''"
    done | sort -u > "$TMP/verweise"
    # sha256sum schreibt 64 Zeichen Prüfsumme und zwei Leerzeichen vor den Pfad
    cut -c 67- "$LIST" | sort -u > "$TMP/gesichert"
    comm -23 "$TMP/verweise" "$TMP/gesichert" > "$TMP/fehlen"
    MISSING=$(wc -l < "$TMP/fehlen" | tr -d ' ')
    FILES=", Dateien: $(wc -l < "$TMP/gesichert" | tr -d ' ') gesichert, $(wc -l < "$TMP/verweise" | tr -d ' ') Verweise, $MISSING fehlen"
    # Merker für backup.sh/run.sh: Dieses Backup ist unvollständig (Gesamtaudit 31.10.b,
    # INF-F03). Alte Backups bleiben dann liegen, und eine Alarm-Mail geht raus.
    if [ "$MISSING" != "0" ]; then
        echo "$MISSING Dateien fehlen im Backup $NAME" > "$DIR/.unvollstaendig"
        {
            echo "$(date '+%F %T') WARNUNG: $NAME zeigt auf $MISSING Dateien, die nicht im Backup stehen:"
            head -n 20 "$TMP/fehlen" | sed 's/^/    /'
        } >> "$DIR/restore-test.log"
        echo "$(date '+%F %T') WARNUNG: $MISSING Dateien fehlen im Backup $NAME (siehe restore-test.log)" \
            >> "$DIR/backup.log"
    fi
fi

KIND="SQL-/Datei-Vortest"
[ "$FULL_RESTORE" = 0 ] || KIND="Sicherungssatzprüfung"
case "${1:-}" in --legacy-*) KIND="LEGACY-Teilprüfung (keine Schlüsselzuordnung)";; esac
RESULT=ok
[ ! -f "$DIR/.unvollstaendig" ] || RESULT=unvollständig
echo "$(date '+%F %T') $KIND $RESULT: $NAME – $ORGS Organisationen, $MEMBERS Mitgliedschaften$FILES" \
    >> "$DIR/restore-test.log"

# The scheduled backup uses its status marker; explicit strict local checks fail.
if [ "$FULL_RESTORE" = 1 ] && [ -f "$DIR/.unvollstaendig" ]; then exit 1; fi
