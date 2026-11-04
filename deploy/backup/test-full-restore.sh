#!/bin/sh
# Synthetic complete-set checks, mounted only by scripts/test.sh (not installed).
set -eu
set -o pipefail
STAGE=initial
trap 'rc=$?; if [ "$rc" != 0 ]; then echo "Full restore test failed ($MODE, stage=$STAGE)" >&2; tail -12 /backups/restore-test.log >&2; [ ! -f /tmp/error ] || cat /tmp/error >&2; fi' EXIT

if [ "$MODE" = age ]; then
    age-keygen -o /tmp/identity 2> /dev/null
    RECIPIENT=$(age-keygen -y /tmp/identity)
fi
backup() {
    if [ "$MODE" = age ]; then
        BACKUP_DATA_KEY_FILE="$1" BACKUP_PUBLIC_KEY="$RECIPIENT" sh "${BACKUP_TEST_PROGRAM:-/usr/local/bin/backup.sh}" > /dev/null
    else
        BACKUP_DATA_KEY_FILE="$1" sh "${BACKUP_TEST_PROGRAM:-/usr/local/bin/backup.sh}" > /dev/null
    fi
}
restore() {
    if [ "$MODE" = age ]; then
        restore-test.sh "--${1}age" "$old" /tmp/identity > /dev/null
    else
        restore-test.sh "--${1}passphrase" "$old" > /dev/null
    fi
}

STAGE=initial-backup
BACKUP_REQUIRE_COMPLETE=1 BACKUP_PRESERVE_EXISTING=1 BACKUP_RECEIPT_NAME=complete backup /run/secrets/datenschluessel
old=$(ls -1t /backups/db_*.sql.gz."$MODE" | head -1)
stamp=$(basename "$old"); stamp=${stamp#db_}; stamp=${stamp%.sql.gz.*}
key="/backups/datenschluessel_$stamp.$MODE"
fingerprint="/backups/datenschluessel_$stamp.sha256"
old_hash=$(cat "$fingerprint")
[ "$(backup-receipt.sh complete)" = "$stamp" ]
cp /backups/complete.receipt /tmp/original-receipt
printf x >> /backups/complete.receipt
if backup-receipt.sh complete > /dev/null 2>&1; then echo "tampered receipt accepted" >&2; exit 1; fi
cp /tmp/original-receipt /backups/complete.receipt
mv "/backups/files_$stamp.tar.gz.$MODE" /tmp/original-files
if backup-receipt.sh complete > /dev/null 2>&1; then echo "incomplete set accepted" >&2; exit 1; fi
mv /tmp/original-files "/backups/files_$stamp.tar.gz.$MODE"
if backup-receipt.sh ../invalid > /dev/null 2>&1; then exit 1; fi
STAGE=strict-original
restore ""
cp "$key" /tmp/original-key
if [ "$MODE" = age ]; then
    printf wrong-key | age -r "$RECIPIENT" > "$key"
else
    printf wrong-key | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
        -pass env:BACKUP_PASSPHRASE -out "$key"
fi
hmac.sh "$key" > "$key.hmac"
STAGE=tampered-key
if restore "" 2> /tmp/error; then echo "wrong key accepted" >&2; exit 1; fi
grep -q 'does not match signed source fingerprint' /tmp/error
cp /tmp/original-key "$key"
hmac.sh "$key" > "$key.hmac"

# Unbound legacy sets must never be labelled as complete strict restores.
STAGE=legacy-fingerprint
mv "$fingerprint" "$fingerprint.saved"
if restore "" 2> /dev/null; then echo "unbound key accepted" >&2; exit 1; fi
STAGE=legacy-restore
restore legacy-
tail -1 /backups/restore-test.log | grep -q 'LEGACY-Teilprüfung'
mv "$fingerprint.saved" "$fingerprint"

# Exchange the live key atomically immediately after the real cp reads it. Only
# the local source copy wraps cp; production has no test hooks or key mutation.
STAGE=key-snapshot-race
cp /run/secrets/datenschluessel /tmp/live-key
printf ABCDEFGHIJKLMNOPQRSTUVWXYZ012345 | base64 > /tmp/replacement-key
python3 - <<'PYSNAPSHOT'
from pathlib import Path
source = Path("/usr/local/bin/backup.sh").read_text()
copy = '''cp() {
    command cp "$@" || return $?
    if [ "${1:-}" = "${BACKUP_DATA_KEY_FILE:-}" ]; then
        command cp /tmp/replacement-key "$BACKUP_DATA_KEY_FILE.new"
        mv "$BACKUP_DATA_KEY_FILE.new" "$BACKUP_DATA_KEY_FILE"
    fi
}
'''
Path("/tmp/snapshot-test.sh").write_text(source.replace("set -eu", copy + "set -eu", 1))
PYSNAPSHOT
BACKUP_TEST_PROGRAM=/tmp/snapshot-test.sh backup /tmp/live-key
previous="$old"
old=$(ls -1t /backups/db_*.sql.gz."$MODE" | head -1)
race_stamp=$(basename "$old"); race_stamp=${race_stamp#db_}; race_stamp=${race_stamp%.sql.gz.*}
[ "$old_hash" = "$(cat "/backups/datenschluessel_$race_stamp.sha256")" ]
[ "$old_hash" != "$(sha256sum /tmp/live-key | cut -d ' ' -f 1)" ]
restore ""
old="$previous"

STAGE=unreadable-key
cp /run/secrets/datenschluessel /tmp/unreadable-key
chmod 000 /tmp/unreadable-key
backup /tmp/unreadable-key
test -f /backups/.unvollstaendig
if BACKUP_REQUIRE_COMPLETE=1 BACKUP_RECEIPT_NAME=invalid backup /tmp/unreadable-key; then echo "strict incomplete backup accepted" >&2; exit 1; fi
test ! -e /backups/invalid.receipt
previous="$old"
old=$(ls -1t /backups/db_*.sql.gz."$MODE" | head -1)
if restore "" 2> /dev/null; then echo "unreadable key accepted" >&2; exit 1; fi
old="$previous"

# Real key-ring rotation retains the old decryption key, with a new write key.
STAGE=key-ring-rotation
printf '# synthetic rotation\n' > /tmp/rotated-key
printf ABCDEFGHIJKLMNOPQRSTUVWXYZ012345 | base64 | tr -d '=' >> /tmp/rotated-key
cat /run/secrets/datenschluessel >> /tmp/rotated-key
backup /tmp/rotated-key
previous="$old"
old=$(ls -1t /backups/db_*.sql.gz."$MODE" | head -1)
[ "$previous" != "$old" ]
restore "" # multiline, commented and unpadded key-ring format is supported
old="$previous"
# Even an unusable latest alias cannot affect restoration of the earlier set.
printf 'deliberately unusable compatibility alias' > "/backups/datenschluessel.$MODE"
hmac.sh "/backups/datenschluessel.$MODE" > "/backups/datenschluessel.$MODE.hmac"
restore ""
[ "$old_hash" = "$(cat "$fingerprint")" ]
[ "$old_hash" != "$(cat /backups/datenschluessel.sha256)" ]
if [ "$MODE" = enc ]; then
    printf '%s\n' "$old" > /backups/test-probe-dump
    printf '%s\n' "$key" > /backups/test-probe-key
fi
echo "Backup: complete $MODE set, tampered key, explicit legacy and rotation checked"
