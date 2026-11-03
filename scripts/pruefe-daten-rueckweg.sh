#!/bin/sh
# Keine Dienste/Container starten: Den gemeinsamen Rückweg mit Compose-Ersatz ausführen.
set -eu
ROOT="$1"
TEMP_TEST=$(mktemp -d)
trap 'rm -rf "$TEMP_TEST"' EXIT
LOG="$TEMP_TEST/aufrufe"
ZIEL_TEST="$TEMP_TEST/ziel mit Leerzeichen"
mkdir -p "$ZIEL_TEST/backend"
touch "$ZIEL_TEST/backend/manage.py"
COMPOSE=mock_compose
STOP_FAIL=0
RUN_FAIL=0
mock_compose() {
    printf '%s|' "$@" >> "$LOG"
    printf '\n' >> "$LOG"
    case "$1" in
        stop) [ "$STOP_FAIL" = 0 ] ;;
        run) [ "$RUN_FAIL" = 0 ] ;;
        *) return 1 ;;
    esac
}
. "$ROOT/deploy/daten-rueckweg.sh"
for file in daten-rueckweg.sh zurueck.sh server-setup.sh; do
    sh -n "$ROOT/deploy/$file"
done

daten_rueckweg "$ZIEL_TEST" > /dev/null
[ "$(wc -l < "$LOG")" -eq 2 ]
head -n 1 "$LOG" | grep -q '^stop|-t|60|backend|worker|beat|backup|$'
tail -n 1 "$LOG" | grep -q -- '--entrypoint|python|'
tail -n 1 "$LOG" | grep -Fq -- "$ZIEL_TEST/backend:/rueckweg-backend:ro|"
tail -n 1 "$LOG" | grep -q -- 'daten_verschluesseln|--rueckweg-zu|/rueckweg-backend|$'

: > "$LOG"
STOP_FAIL=1
if daten_rueckweg "$ZIEL_TEST" > /dev/null; then exit 1; fi
[ "$(wc -l < "$LOG")" -eq 1 ]

: > "$LOG"
STOP_FAIL=0
RUN_FAIL=1
if daten_rueckweg "$ZIEL_TEST" > /dev/null; then exit 1; fi
[ "$(wc -l < "$LOG")" -eq 2 ]

: > "$LOG"
if daten_rueckweg "$TEMP_TEST/fehlt" > /dev/null 2>&1; then exit 1; fi
[ ! -s "$LOG" ]

# Beide Betriebswege müssen denselben geprüften Baustein nutzen; keinen pauschalen
# Datenbank-Entschlüsselungsbefehl als alternativen Fehlerpfad einführen.
for file in "$ROOT/deploy/zurueck.sh" "$ROOT/deploy/server-setup.sh"; do
    grep -q 'daten_rueckweg "\$ZIEL.vorher"' "$file"
    if grep -q 'daten_verschluesseln --entschluesseln' "$file"; then exit 1; fi
done
echo "Daten-Rückweg: Stoppen, Zielfassung, Fehlerpfade und Shellsyntax ok"
