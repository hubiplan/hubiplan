#!/bin/sh
# Prüft den genau zugeordneten vollständigen Sicherungssatz; kein privater age-Key nötig.
set -eu
DIR=${BACKUP_DIR:-/backups}
NAME=${1:?Backup-Nachweisname fehlt}
case "$NAME" in ''|*[!a-zA-Z0-9_-]*) echo "Ungültiger Backup-Nachweisname" >&2; exit 1;; esac
RECEIPT="$DIR/$NAME.receipt"
verify.sh "$RECEIPT"
[ "$(wc -l < "$RECEIPT" | tr -d ' ')" = 2 ] || exit 1
STAMP=$(sed -n '1p' "$RECEIPT")
EXT=$(sed -n '2p' "$RECEIPT")
printf '%s\n' "$STAMP" | grep -Eq '^[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{6}_[0-9a-f]{12}$' || exit 1
case "$EXT" in enc|age) ;; *) exit 1;; esac
for artifact in "db_$STAMP.sql.gz.$EXT" "files_$STAMP.tar.gz.$EXT" \
    "dateien_$STAMP.sha256.$EXT" "datenschluessel_$STAMP.$EXT" "datenschluessel_$STAMP.sha256"; do
    verify.sh "$DIR/$artifact"
done
printf '%s\n' "$STAMP"
