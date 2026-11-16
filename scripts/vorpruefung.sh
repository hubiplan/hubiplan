#!/usr/bin/env bash
# Schnelle Vorprüfung eines Commits, ohne Testplatz (docs/testserver.md, „Vorprüfung“):
#
#   scripts/vorpruefung.sh [Git-Referenz]
#
# Prüft in Sekunden bis etwa zwei Minuten, woran volle Läufe am häufigsten scheitern:
# - Backend: ruff check und ruff format --check
# - Frontend: Typprüfung, Lint, Format, i18n-Prüfung, die Hilfe-Tests (erzeugte
#   backend/mcpserver/hilfe.json aktuell, Fettschrift-Namen) und die Vitest-Dateien, die der
#   Stand gegenüber main ändert
# Sie belegt keinen Testplatz und nutzt höchstens VORPRUEFUNG_KERNE (2) Kerne mit niedriger
# Priorität. Sie ist nie eine Freigabe zum Ausrollen; das bleibt scripts/test.sh.
# scripts/test.sh ruft sie vor der Warteschlange auf. Ein grüner Stand wird vermerkt und nicht
# noch einmal geprüft.
#
# Ohne Docker (z. B. in einer Cloud-Sitzung) oder mit VORPRUEFUNG_OHNE_DOCKER=1 läuft sie mit
# dem installierten node/npm und ruff (pip install ruff in der Fassung aus requirements-dev.txt).
set -euo pipefail

REF="${1:-HEAD}"
COMMIT=$(git rev-parse --verify --quiet "$REF^{commit}") || { echo "Vorprüfung: $REF fehlt." >&2; exit 2; }
SHA=$(git rev-parse --short "$COMMIT")
TREE=$(git rev-parse "$COMMIT^{tree}")
STATE_DIR="$(dirname "${HUBIPLAN_TESTED_FILE:-$HOME/.local/state/hubiplan/tested-trees}")"
VERMERK="$STATE_DIR/vorgeprueft"
if grep -q "^$TREE " "$VERMERK" 2> /dev/null; then
    echo "Vorprüfung: $SHA schon grün."
    exit 0
fi
KERNE="${VORPRUEFUNG_KERNE:-2}"
start=$(date +%s)

DOCKER=1
if [ "${VORPRUEFUNG_OHNE_DOCKER:-0}" = 1 ] || ! docker info > /dev/null 2>&1; then DOCKER=0; fi

WORK=$(mktemp -d)
NAME="hubiplan-vorpruefung-$(date +%s)-$$"
cleanup() {
    [ "$DOCKER" = 1 ] && docker rm -f "$NAME-fe" "$NAME-be" > /dev/null 2>&1 || true
    rm -rf "$WORK" 2> /dev/null \
        || docker run --rm -v "$WORK:/w" node:24-alpine rm -rf /w/backend /w/frontend
    rm -rf "$WORK"
}
trap cleanup EXIT
trap 'exit 143' TERM INT HUP
git archive --format=tar "$COMMIT" backend frontend | tar -x -C "$WORK"

# Geänderte Vitest-Dateien gegenüber main (höchstens 20), wie der Backend-Vorlauf in test.sh
basis=""
for r in refs/test-main/main origin/main main; do
    basis=$(git merge-base "$COMMIT" "$r" 2> /dev/null) && break
    basis=""
done
GEAENDERT=()
if [ -n "$basis" ] && [ "$basis" != "$COMMIT" ]; then
    mapfile -t GEAENDERT < <(git diff --name-only --diff-filter=AMR "$basis" "$COMMIT" -- \
        'frontend/src/test/*.test.ts' 'frontend/src/test/*.test.tsx' | sed 's#^frontend/##')
    [ "${#GEAENDERT[@]}" -le 20 ] || GEAENDERT=()
fi
VITEST="src/test/McpHilfe.test.ts src/test/Hilfe.test.tsx ${GEAENDERT[*]}"

RUFF=$(grep -m1 -oE '^ruff==[0-9.]+' "$WORK/backend/requirements-dev.txt")
FE_BEFEHL="npm ci --no-audit --no-fund --loglevel=error > /dev/null \
    && npm run -s typecheck && npm run -s lint > /dev/null && npm run -s format:check > /dev/null \
    && npm run -s i18n:check && npx vitest run --maxWorkers=$KERNE --reporter=dot $VITEST"

rc=0
if [ "$DOCKER" = 1 ]; then
    # Nur so viele Kerne, wie die Vorprüfung darf, und mit niedrigem CPU-Anteil, damit sie die
    # Testplätze nicht ausbremst
    BEGRENZT=(--cpus "$KERNE" --cpu-shares 128 --label "hubiplan.vorpruefung=$NAME")
    # ruff: genau die festgeschriebene Fassung (mit Prüfsumme) aus requirements-dev.txt
    awk -v p="$RUFF" 'index($0, p) == 1 { f = 1; print; next } f && /^[[:space:]]+--hash/ { print; next } { f = 0 }' \
        "$WORK/backend/requirements-dev.txt" | sed 's/ \\$//' > "$WORK/ruff-req.txt"
    docker run --rm --name "$NAME-be" "${BEGRENZT[@]}" -v "$WORK/backend:/app" -w /app \
        -v hubiplan-pip-cache:/root/.cache/pip --entrypoint sh \
        "$(grep -m1 -oE '^FROM [^ ]+' "$WORK/backend/Dockerfile" | cut -d' ' -f2)" -c \
        "pip install -q --disable-pip-version-check --require-hashes --no-deps -r /app/../app/ruff-req.txt 2> /dev/null \
         || pip install -q --disable-pip-version-check '$RUFF'; ruff check . && ruff format --check ." \
        < /dev/null || rc=$?
    if [ "$rc" = 0 ]; then
        echo "Vorprüfung Backend: ruff ok"
        docker run --rm --name "$NAME-fe" "${BEGRENZT[@]}" -v "$WORK/frontend:/app" \
            -v "$WORK/backend:/backend:ro" -v hubiplan-npm-cache:/root/.npm -w /app \
            node:24-alpine sh -c "$FE_BEFEHL" < /dev/null || rc=$?
    fi
else
    command -v npm > /dev/null || { echo "Vorprüfung: npm fehlt" >&2; exit 2; }
    # Genau die Fassung aus requirements-dev.txt; eine andere formatiert anders
    RUFF_BIN=ruff
    if [ "$(ruff --version 2> /dev/null | cut -d' ' -f2)" != "${RUFF#ruff==}" ]; then
        venv="${XDG_CACHE_HOME:-$HOME/.cache}/hubiplan/$RUFF"
        [ -x "$venv/bin/ruff" ] || { python3 -m venv "$venv" && "$venv/bin/pip" install -q "$RUFF"; } \
            || { echo "Vorprüfung: $RUFF ließ sich nicht installieren" >&2; exit 2; }
        RUFF_BIN="$venv/bin/ruff"
    fi
    (cd "$WORK/backend" && nice "$RUFF_BIN" check . && nice "$RUFF_BIN" format --check .) || rc=$?
    if [ "$rc" = 0 ]; then
        echo "Vorprüfung Backend: ruff ok"
        (cd "$WORK/frontend" && nice sh -c "$FE_BEFEHL") || rc=$?
    fi
fi
if [ "$rc" != 0 ]; then
    echo "Vorprüfung ROT für $SHA (nach $(($(date +%s) - start)) s): erst beheben, dann scripts/test.sh." >&2
    echo "Hinweis: Hilfe geändert → im Ordner frontend node scripts/mcp-hilfe.mjs und einchecken;" \
        "Format → npx prettier --write src; Backend → ruff format ." >&2
    exit "$rc"
fi
mkdir -p "$STATE_DIR"
echo "$TREE $SHA $(date -Iseconds)" >> "$VERMERK"
echo "Vorprüfung grün: $SHA ($(($(date +%s) - start)) s)"
