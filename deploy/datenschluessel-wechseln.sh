#!/usr/bin/env bash
# Auf dem Server im ausgerollten Checkout ausführen. Keine Tests/kein Ausrollen.
set -euo pipefail
umask 077
ORG= MODE=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --organisation) ORG=${2:-}; shift 2 ;;
        --starten|--fortsetzen) [ -z "$MODE" ] || exit 2; MODE=${1#--}; shift ;;
        *) echo "Aufruf: bash deploy/datenschluessel-wechseln.sh --organisation NUMMER --starten|--fortsetzen" >&2; exit 2 ;;
    esac
done
[[ "$ORG" =~ ^[1-9][0-9]*$ ]] && [ -n "$MODE" ] || exit 2
ZIEL=$(pwd -P)
[ -f .env ] && [ -f docker-compose.server.yml ] && [ -f .fassung ] || {
    echo "Im ausgerollten Checkout mit .env und .fassung ausführen." >&2; exit 1;
}
VERSION=$(cat .fassung)
[[ "$VERSION" =~ ^[0-9a-f]{40}$ ]] || exit 1
STATE_DIR="$ZIEL.datenschluesselwechsel"
STATUS="$STATE_DIR/status"
OPEN="$STATE_DIR/offen"
LOCK="$ZIEL.sperre"
[ ! -L "$STATE_DIR" ] && [ ! -L "$STATUS" ] && [ ! -L "$OPEN" ] || exit 1
env_value() { sed -n "s/^$1=//p" .env; }
PROJECT=$(env_value COMPOSE_PROJECT_NAME)
PROJECT=${PROJECT:-$(basename "$ZIEL")}
COMPOSE=(docker compose --project-directory "$ZIEL" -p "$PROJECT" -f docker-compose.server.yml)
[ "$(env_value HUBIPLAN_HINTER_PROXY)" != 1 ] || COMPOSE+=(-f docker-compose.proxy.yml)
[ -z "$(env_value CLAMD_SOCKET_DIR)" ] || COMPOSE+=(-f docker-compose.clamav.yml)
[ "$(env_value HUBIPLAN_SELBSTUPDATE)" != 1 ] || COMPOSE+=(-f docker-compose.selbstupdate.yml)
compose() { "${COMPOSE[@]}" "$@"; }
manage() { compose run -T --rm --no-deps --entrypoint python backend manage.py datenschluessel_wechseln --organisation "$ORG" "$@"; }
read_state() { sed -n "s/^$1=//p" "$STATUS"; }
PHASE=vorbereitung TOKEN= BASELINE= BEFORE= AFTER=
PAUSE=0 SUCCESS=0
mkdir "$LOCK" 2>/dev/null || { echo "Ein Deploy oder Wartungslauf hält bereits die Betriebssperre." >&2; exit 1; }
cleanup() {
    local rc=$?
    trap - EXIT
    if [ "$SUCCESS" != 1 ] && [ "$PAUSE" = 1 ]; then
        compose stop -t 60 backend worker beat backup >&2 || true
        echo "Schreibpause bleibt bestehen. Ursache beheben; danach: bash deploy/datenschluessel-wechseln.sh --organisation $ORG --fortsetzen" >&2
    fi
    rm -f "$LOCK/lauf"
    rmdir "$LOCK" || true
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
printf 'Datenschluesselwechsel %s\n' "$ORG" > "$LOCK/lauf"
save_state() {
    printf 'format=1\norganisation=%s\nversion=%s\ntoken=%s\nbaseline=%s\nphase=%s\nbefore=%s\nafter=%s\n' \
        "$ORG" "$VERSION" "$TOKEN" "$BASELINE" "$PHASE" "$BEFORE" "$AFTER" > "$STATUS.tmp"
    sync -f "$STATUS.tmp"
    mv "$STATUS.tmp" "$STATUS"
    sync -f "$STATE_DIR"
}
status_id() {
    local status
    status=$(manage --status)
    [[ "$status" =~ ^([0-9]+)\ (none|running|completed)$ ]] || {
        echo "Ungültige Auftragsauskunft; keine automatische Fortsetzung." >&2; return 1;
    }
    printf '%s\n' "${BASH_REMATCH[1]}"
}
if [ "$MODE" = starten ]; then
    [ ! -e "$STATUS" ] && [ ! -e "$OPEN" ] || { echo "Ein Wartungslauf ist offen; --fortsetzen verwenden." >&2; exit 1; }
    INITIAL_STATUS=$(manage --status)
    [[ "$INITIAL_STATUS" =~ ^([0-9]+)\ (none|completed)$ ]] || {
        echo "Datenauftrag bereits offen oder Status unklar; keinen neuen Wartungslauf beginnen." >&2; exit 1;
    }
    BASELINE=${BASH_REMATCH[1]}
    TOKEN=$(openssl rand -hex 12)
    mkdir -p "$STATE_DIR"
    chmod 700 "$STATE_DIR"
else
    [ -f "$STATUS" ] && [ "$(read_state format)" = 1 ] \
        && [ "$(read_state organisation)" = "$ORG" ] \
        && [ "$(read_state version)" = "$VERSION" ] || {
        echo "Passender Wartungsvermerk dieser Fassung fehlt; nicht automatisch fortsetzen." >&2; exit 1;
    }
    TOKEN=$(read_state token); BASELINE=$(read_state baseline)
    BEFORE=$(read_state before); AFTER=$(read_state after)
    [[ "$TOKEN" =~ ^[0-9a-f]{24}$ ]] && [[ "$BASELINE" =~ ^[0-9]+$ ]] || exit 1
fi
mkdir -p "$OPEN"
sync -f "$STATE_DIR"
PAUSE=1
save_state
compose stop -t 60 backend worker beat backup
ensure_stopped() {
    [ -z "$(compose ps --status running -q backend worker beat backup)" ] || {
        echo "Schreibdienste sind noch aktiv; Wechsel abgebrochen." >&2; return 1;
    }
}
ensure_stopped
receipt() {
    compose run -T --rm --no-deps --entrypoint backup-receipt.sh backup "$1"
}
backup_set() {
    ensure_stopped
    compose run -T --rm --no-deps \
        -e BACKUP_REQUIRE_COMPLETE=1 -e BACKUP_PRESERVE_EXISTING=1 \
        -e "BACKUP_RECEIPT_NAME=$1" --entrypoint backup.sh backup
}
if [ -z "$BEFORE" ]; then
    # Einen neuen 'Vorher'-Satz nur anlegen, solange noch kein neuer Auftrag existiert.
    [ "$(status_id)" = "$BASELINE" ] || { echo "Vorher-Nachweis fehlt bei verändertem Schlüsselauftrag." >&2; exit 1; }
    PHASE=backup_vorher; save_state
    backup_set "$TOKEN-vorher"
    BEFORE=$(receipt "$TOKEN-vorher")
    [[ "$BEFORE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{6}_[0-9a-f]{12}$ ]] || exit 1
    save_state
fi
[ "$(receipt "$TOKEN-vorher")" = "$BEFORE" ] || exit 1
ensure_stopped
PHASE=vorpruefung; save_state
manage --probe
PHASE=wechsel; save_state
CURRENT=$(status_id)
if [ "$CURRENT" = "$BASELINE" ]; then
    manage --starten --schreiber-angehalten
elif [ "$CURRENT" -gt "$BASELINE" ]; then
    manage --schreiber-angehalten
else
    echo "Auftragshistorie verändert; nicht automatisch fortsetzen." >&2; exit 1
fi
ensure_stopped
PHASE=abschlusspruefung; save_state
manage --pruefen
PHASE=backup_nachher; save_state
backup_set "$TOKEN-nachher"
AFTER=$(receipt "$TOKEN-nachher")
[[ "$AFTER" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{6}_[0-9a-f]{12}$ ]] || exit 1
[ "$(receipt "$TOKEN-vorher")" = "$BEFORE" ] || exit 1
PHASE=neustart; save_state
ensure_stopped
manage --pruefen
compose up -d --no-deps --wait --wait-timeout 300 backend
compose up -d --no-deps --wait --wait-timeout 300 worker beat backup
PHASE=abgeschlossen; save_state
rmdir "$OPEN"
mv "$STATUS" "$STATE_DIR/letzter-abschluss"
sync -f "$STATE_DIR"
SUCCESS=1
echo "Schlüsselwechsel und Neustart geprüft. Sicherungssätze: vorher $BEFORE; nachher $AFTER. Alte Schlüssel bleiben erhalten."
