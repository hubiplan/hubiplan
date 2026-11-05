#!/usr/bin/env bash
# Von scripts/test.sh im belegten lokalen Testplatz aufrufen (gemeinsame Variablen).
set -euo pipefail
ROT_DATA="$ID-rotation-data"
ROT_RESTORE="$ID-rotation-restore"
ROT_BACKUPS="$ID-rotation-backups"
docker volume create "$ROT_DATA" > /dev/null
docker volume create "$ROT_RESTORE" > /dev/null
docker volume create "$ROT_BACKUPS" > /dev/null
docker run --rm --user 0 "$CPUS" -v "$ROT_DATA:/data" -v "$ROT_BACKUPS:/backups" \
    --entrypoint sh "$BACKUP_IMG" -c 'chown 1000:1000 /data; chown 70:70 /backups'
docker exec "$ID-db" createdb -U test hubiplan_rotation
rot_app() {
    local db=$1 volume=$2 key=$3 mode=$4
    docker run --rm --network "$ID" "$CPUS" -e DJANGO_DEBUG=true -e DJANGO_SECRET_KEY=nur-test \
        -e "DATABASE_URL=postgres://test:test@$ID-db:5432/$db" \
        -v "$volume:/data" -e PRIVATE_ROOT=/data/private -e MEDIA_ROOT=/data/media \
        -v "$key:/run/secrets/datenschluessel:ro" -e DATA_ENCRYPTION_KEY_FILE=/run/secrets/datenschluessel \
        -v "$WORK/deploy/backup/test_key_rotation.py:/tmp/test_key_rotation.py:ro" \
        --entrypoint sh "$BACKEND_IMG" -c 'python /tmp/test_key_rotation.py "$1"' sh "$mode"
}
docker run --rm --network "$ID" "$CPUS" -e DJANGO_DEBUG=true -e DJANGO_SECRET_KEY=nur-test \
    -e "DATABASE_URL=postgres://test:test@$ID-db:5432/hubiplan_rotation" --entrypoint python \
    "$BACKEND_IMG" manage.py migrate -v0
rot_app hubiplan_rotation "$ROT_DATA" "$WORK/test-data-key" seed
EXPECTED=$(rot_app hubiplan_rotation "$ROT_DATA" "$WORK/test-data-key" fingerprint)
for stage in before during after; do
    case "$stage" in
        during) rot_app hubiplan_rotation "$ROT_DATA" "$WORK/test-data-key" interrupt ;;
        after) rot_app hubiplan_rotation "$ROT_DATA" "$WORK/test-data-key" finish ;;
    esac
    for mode in enc age; do
        docker run --rm --group-add 1000 --network "$ID" "$CPUS" --tmpfs /tmp -v "$ROT_BACKUPS:/backups" \
            -v "$ROT_DATA:/data:ro" -v "$WORK/test-data-key:/run/secrets/datenschluessel:ro" \
            -e PGHOST="$ID-db" -e PGUSER=test -e PGPASSWORD=test -e PGDATABASE=hubiplan_rotation \
            -e BACKUP_PASSPHRASE=nur-test -e BACKUP_HMAC_KEY=nur-test \
            -e MODE="$mode" -e BACKUP_DIR="/backups/$stage-$mode" \
            --entrypoint sh "$BACKUP_IMG" -c 'set -eu; set -o pipefail
                if [ "$MODE" = age ]; then
                    age-keygen -o "$BACKUP_DIR.key" 2>/dev/null
                    export BACKUP_PUBLIC_KEY=$(age-keygen -y "$BACKUP_DIR.key")
                fi
                BACKUP_REQUIRE_COMPLETE=1 BACKUP_PRESERVE_EXISTING=1 BACKUP_RECEIPT_NAME=rotation backup.sh > /dev/null
                stamp=$(backup-receipt.sh rotation)
                dump="$BACKUP_DIR/db_$stamp.sql.gz.$MODE"
                if [ "$MODE" = age ]; then
                    restore-test.sh --age "$dump" "$BACKUP_DIR.key"
                else
                    restore-test.sh --passphrase "$dump"
                fi
                # Satzgebundene Kopie: Schlüssel aus genau dieser Sicherung verwenden.
                decrypt() {
                    if [ "$MODE" = age ]; then age -d -i "$BACKUP_DIR.key" "$1"
                    else openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE -in "$1"; fi
                }
                decrypt "$BACKUP_DIR/datenschluessel_$stamp.$MODE" > /backups/recovered-key
                decrypt "$dump" | gunzip > /backups/recovered.sql
                decrypt "$BACKUP_DIR/files_$stamp.tar.gz.$MODE" > /backups/recovered-files.tar.gz
                chmod 644 /backups/recovered-key /backups/recovered.sql /backups/recovered-files.tar.gz'
        docker exec "$ID-db" dropdb --if-exists -U test hubiplan_rotation_restore
        docker exec "$ID-db" createdb -U test hubiplan_rotation_restore
        docker run --rm "$CPUS" -v "$ROT_BACKUPS:/backups:ro" --entrypoint cat "$BACKUP_IMG" /backups/recovered.sql \
            | docker exec -i "$ID-db" psql -q -U test -d hubiplan_rotation_restore -v ON_ERROR_STOP=1 > /dev/null
        # Beide Volumes sind ausschließlich von diesem lokalen Testlauf erzeugt.
        docker run --rm --user 0 "$CPUS" -v "$ROT_BACKUPS:/backups:ro" -v "$ROT_RESTORE:/data" \
            --entrypoint sh "$BACKUP_IMG" -c 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} +; tar -xzf /backups/recovered-files.tar.gz -C /data; chown -R 1000:1000 /data'
        docker run --rm "$CPUS" -v "$ROT_BACKUPS:/backups:ro" --entrypoint cat "$BACKUP_IMG" /backups/recovered-key > "$WORK/rotation-recovered-key"
        chmod 644 "$WORK/rotation-recovered-key"
        ACTUAL=$(rot_app hubiplan_rotation_restore "$ROT_RESTORE" "$WORK/rotation-recovered-key" "restore-$stage")
        [ "$EXPECTED" = "$ACTUAL" ] || { echo "Wiederhergestellter Rotationsbestand verändert ($stage/$mode)" >&2; exit 1; }
        echo "Schlüsselwechsel-Restore: $stage/$mode mit wiederhergestelltem Satzschlüssel und unverändertem Inhalt geprüft"
    done
done
rot_app hubiplan_rotation "$ROT_DATA" "$WORK/test-data-key" benchmark
