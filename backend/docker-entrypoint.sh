#!/bin/sh
set -e

# Migrationen nur im Web-Container ausführen, nicht im Worker.
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    # Migrationen laufen als Tabelleneigentümer, nicht in der RLS-Rolle. Auf dem
    # Server steht dessen Zugang nur in MIGRATE_DATABASE_URL; die laufende
    # Anwendung meldet sich danach als hubiplan_app an (DATABASE_URL).
    OWNER_URL="${MIGRATE_DATABASE_URL:-${DATABASE_URL:-}}"
    # Ein Prozess für Migrationen, Rolle und Löschliste (spart Startzeit beim Ausrollen).
    # MIGRATE_PGOPTIONS (z. B. „-c lock_timeout=15s“) setzt deploy/server-setup.sh nur für
    # den eigenen Migrationsschritt: Eine Migration wartet dann nicht endlos auf eine Sperre.
    DATABASE_URL="$OWNER_URL" DATABASE_APP_ROLE= PGOPTIONS="${MIGRATE_PGOPTIONS:-${PGOPTIONS:-}}" \
        python manage.py startvorbereitung -v "${MIGRATE_VERBOSITY:-1}"
    unset OWNER_URL
fi
# Schlüsseldateien älterer Fassungen (0600) für die Gruppe lesbar machen, damit das
# Backup sie mitsichern kann (siehe peering/identity.py, KEY_FILE_MODE)
if [ -d /app/private ]; then
    find /app/private -type f -user "$(id -u)" -perm 0600 -exec chmod 0640 {} + 2> /dev/null || true
fi
# Reste abgebrochener Uploads entfernen (älter als einen Tag)
if [ -d /app/upload-tmp ]; then
    find /app/upload-tmp -type f -mmin +1440 -delete 2> /dev/null || true
fi
# Der Zugang des Tabelleneigentümers gelangt nicht in den laufenden Prozess
unset MIGRATE_DATABASE_URL APP_DB_PASSWORD

# Statische Dateien (Admin, API-Doku) für den Betrieb mit gunicorn einsammeln.
if [ "${COLLECT_STATIC:-0}" = "1" ]; then
    python manage.py collectstatic --noinput
fi

exec "$@"
