#!/usr/bin/env bash
# Muss ein grün getesteter Zweig nach fremden Merges in main noch einmal getestet werden?
#
#   scripts/nachtest-noetig.sh [getesteter Commit] [main-Referenz]
#
# Vorgaben: HEAD und origin/main. Verglichen werden die Änderungen des Zweigs (seit der
# gemeinsamen Basis mit main) mit dem, was main seitdem dazubekommen hat. Ein Nachtest ist
# nötig, wenn sich etwas überschneidet:
#   - dieselbe Datei (außer Übersetzungskatalogen und Doku),
#   - Migrationen derselben App,
#   - eine Datei, von der ein ganzer Teil abhängt (Abhängigkeiten, conftest/factories, RLS,
#     Testskript, Docker, Frontend-Konfiguration und Testhilfen), wenn die andere Seite in
#     demselben Teil etwas ändert.
# Exit 0: kein Nachtest nötig, direkt mergen (GitHub muss konfliktfrei melden).
# Exit 1: main einmischen und scripts/test.sh erneut ausführen; die Gründe stehen in der Ausgabe.
# Den gemergten main prüft danach `scripts/test.sh --main` vor dem Ausrollen (docs/testserver.md).
set -euo pipefail

ZWEIG=$(git rev-parse --verify "${1:-HEAD}^{commit}")
MAIN=$(git rev-parse --verify "${2:-origin/main}^{commit}")
BASIS=$(git merge-base "$ZWEIG" "$MAIN")

if [ "$BASIS" = "$MAIN" ]; then
    echo "Kein Nachtest nötig: main hat seit dem getesteten Stand nichts Neues."
    exit 0
fi

# Dateien, von denen ein ganzer Teil abhängt. Ändert eine Seite eine davon, muss die andere
# Seite neu testen, wenn sie in demselben Teil (Backend oder Frontend) etwas geändert hat.
GLOBAL_B='^(backend/requirements[^/]*|backend/Dockerfile|backend/pyproject\.toml|backend/tests/(conftest|factories)\.py|backend/core/rls\.py|scripts/test\.sh|docker-compose[^/]*)$'
GLOBAL_F='^(frontend/(package(-lock)?\.json|vite[^/]*|tsconfig[^/]*|eslint[^/]*|src/test/setup\.ts|scripts/.*)|scripts/test\.sh)$'
FRONTEND='^frontend/'
BACKEND='^(backend|deploy|scripts)/'

zweig=$(git diff --name-only "$BASIS" "$ZWEIG")
neu=$(git diff --name-only "$BASIS" "$MAIN")
gruende=()

# Übersetzungskataloge, Hilfe und Doku zählen nicht: Ohne Git-Konflikt ergänzen sich dort nur
# Einträge, und i18n:check / uebersetzung_pruefen laufen im main-Lauf ohnehin.
OHNE='^(frontend/src/i18n/[^/]+\.json|backend/locale/.*\.po|docs/.*|frontend/src/help/.*\.md|[^/]+\.md)$'
gleich=$(comm -12 <(sort -u <<< "$zweig") <(sort -u <<< "$neu") | grep -vE "$OHNE" | sed '/^$/d' || true)
[ -z "$gleich" ] || gruende+=("dieselben Dateien geändert:" "$(sed 's/^/    /' <<< "$gleich")")

apps() { grep -oE '^backend/[^/]+/migrations/' <<< "$1" | sort -u || true; }
mig=$(comm -12 <(apps "$zweig") <(apps "$neu") | sed '/^$/d')
[ -z "$mig" ] || gruende+=("Migrationen derselben App:" "$(sed 's/^/    /' <<< "$mig")")

# Globale Dateien der einen Seite treffen die andere nur in deren Teil
global=""
pruefe_global() { # $1 Muster global, $2 Muster Teil
    local g
    if grep -qE "$2" <<< "$zweig"; then
        g=$(grep -E "$1" <<< "$neu" || true)
        [ -z "$g" ] || global+="$g"$'\n'
    fi
    if grep -qE "$2" <<< "$neu"; then
        g=$(grep -E "$1" <<< "$zweig" || true)
        [ -z "$g" ] || global+="$g"$'\n'
    fi
}
pruefe_global "$GLOBAL_B" "$BACKEND"
pruefe_global "$GLOBAL_F" "$FRONTEND"
global=$(sort -u <<< "$global" | sed '/^$/d')
[ -z "$global" ] || gruende+=("Dateien, von denen ein ganzer Teil abhängt:" "$(sed 's/^/    /' <<< "$global")")

n=$(git rev-list --count "$BASIS..$MAIN")
if [ "${#gruende[@]}" -eq 0 ]; then
    echo "Kein Nachtest nötig: main hat $n neue Commits, aber nichts überschneidet sich mit dem Zweig."
    exit 0
fi
echo "Nachtest nötig: main hat $n neue Commits, und es gibt Überschneidungen."
printf '%s\n' "${gruende[@]}"
exit 1
