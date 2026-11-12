#!/usr/bin/env bash
# Zentrales Test-Skript: prüft einen Commit lokal in WSL (Docker), bevor er
# ausgerollt wird. Alle Sitzungen nutzen nur dieses Skript.
#
#   scripts/test.sh [Git-Referenz] [pytest-Argumente]
#
# - Backend: ruff und pytest gegen PostgreSQL 18 in Wegwerf-Containern
# - Frontend: Typprüfung, Lint, Formatierung und Tests im Node-Container
# - BACKUP_TEST=1: zusätzlich Backup und Rücksicherung mit Demodaten
#
# Es läuft nur, was eingecheckt ist (git archive). Nach Erfolg wird der Stand
# (Git-Tree) als getestet vermerkt; deploy/deploy.sh rollt nur solche Stände aus.
#
# Die Frontend-Prüfungen ohne Tests (Typen, Lint, Format) laufen gleichzeitig mit dem
# Backend (TEST_PARALLEL=0: alles nacheinander).
#
# Regeln: Tests laufen nie auf dem Testserver. Das Skript holt sich einen Testplatz über
# scripts/testplatz.sh (Plätze und Kerne lokal eingestellt) und bindet alle Container
# an dessen Kerne.
set -euo pipefail

# Release-Commit (docs/releases.md): Ändert ein Commit gegenüber seinem schon getesteten
# Vorgänger nur CHANGELOG.md/CHANGELOG.en.md, gilt er ohne neuen Lauf als getestet. Programm
# und Tests sind dann dieselben; so belegt ein Release keinen Testplatz.
STATE="${HUBIPLAN_TESTED_FILE:-$HOME/.local/state/hubiplan/tested-trees}"
nur_aenderungshinweise() {
    local c p dateien
    c=$(git rev-parse --verify --quiet "$1^{commit}" 2> /dev/null) || return 1
    p=$(git rev-parse --verify --quiet "$c^1^{commit}" 2> /dev/null) || return 1
    # Merge-Commits nicht (deren zweiter Elternteil ist ungeprüft)
    git rev-parse --verify --quiet "$c^2" > /dev/null 2>&1 && return 1
    grep -q "^$(git rev-parse "$p^{tree}") " "$STATE" 2> /dev/null || return 1
    dateien=$(git diff --name-only "$p" "$c")
    [ -n "$dateien" ] && ! grep -qvxE 'CHANGELOG(\.en)?\.md' <<< "$dateien"
}
if [ "$#" -le 1 ] && nur_aenderungshinweise "${1:-HEAD}"; then
    c=$(git rev-parse "${1:-HEAD}^{commit}")
    echo "$(git rev-parse "$c^{tree}") $(git rev-parse --short "$c") $(date -Iseconds) nur-aenderungshinweise" >> "$STATE"
    echo "Alles grün: $(git rev-parse --short "$c") ändert gegenüber dem getesteten Vorgänger nur die Änderungshinweise und ist als getestet vermerkt."
    exit 0
fi

# Teile (docs/testserver.md, „Nur geänderte Teile“): Backend und Frontend werden je für
# sich als grün vermerkt, mit einem Schlüssel über genau die Dateien, die in ihre Prüfungen
# eingehen. Ein Stand gilt als getestet, wenn jeder Teil mit genau diesem Inhalt schon grün
# war. Die Zuordnung ist bewusst großzügig: Backend ist alles außer frontend/, docs/ und
# den Markdown-Dateien im Hauptverzeichnis; Frontend ist frontend/, dieses Skript und die
# Backend-Dateien, die der Frontend-Code beim Namen nennt (z. B. learning_keys.json).
# TEST_ALLES=1 prüft immer alles (vor einem Release).
PARTS="${HUBIPLAN_TESTED_PARTS_FILE:-$(dirname "$STATE")/tested-parts}"
teil_schluessel() {
    local pfade
    case "$1" in
        backend)
            git ls-tree -r "$2" | awk -F '\t' '$2 !~ /^"?(frontend|docs)\// && $2 !~ /^"?[^\/]+\.md"?$/' ;;
        frontend)
            pfade=$(git grep -ohE 'backend/[A-Za-z0-9_./-]+' "$2" -- frontend | sort -u || true)
            # shellcheck disable=SC2086 # Pfade ohne Leerzeichen
            git ls-tree -r "$2" -- frontend scripts/test.sh $pfade ;;
    esac | sha256sum | cut -c1-16
}
teil_gruen() { grep -q "^$1 $2 " "$PARTS" 2> /dev/null; }
teile_schon_gruen() {
    teil_gruen backend "$(teil_schluessel backend "$1")" && teil_gruen frontend "$(teil_schluessel frontend "$1")"
}
schon_gruen_vermerken() {
    mkdir -p "$(dirname "$STATE")"
    echo "$(git rev-parse "$1^{tree}") $(git rev-parse --short "$1") $(date -Iseconds) teile-schon-gruen" >> "$STATE"
    echo "Alles grün: $(git rev-parse --short "$1") hat Backend und Frontend mit einem Inhalt, der schon grün war, und ist als getestet vermerkt."
    exit 0
}
LAUFEND="$(dirname "$STATE")/laufend"

# --main (docs/testserver.md, „Merge und main“): den neuesten main testen, gebündelt. Es läuft
# immer nur ein main-Lauf; wer danach kommt, holt main neu. Ist der neueste main dann schon
# getestet (er enthält den eigenen Merge), ist nichts mehr zu tun.
if [ "${1:-}" = "--main" ] && [ -z "${TESTPLATZ:-}" ]; then
    [ "$#" -eq 1 ] || { echo "Abbruch: --main nimmt keine weiteren Argumente." >&2; exit 2; }
    main_holen() {
        local url ref
        url=$(git remote get-url origin 2> /dev/null || true)
        if [ -n "${TEST_MAIN_REF:-}" ]; then
            git fetch --all --quiet || echo "Warnung: git fetch ist fehlgeschlagen." >&2
            ref=$TEST_MAIN_REF
        elif [ -d "$url" ]; then
            # origin ist ein lokaler Klon (WSL-Klon vom Windows-Klon): dort von GitHub holen und
            # dessen origin/main nehmen, nicht seinen lokalen, womöglich veralteten main
            git -C "$url" fetch --quiet origin || echo "Warnung: git fetch in $url ist fehlgeschlagen." >&2
            git fetch --quiet origin "+refs/remotes/origin/main:refs/test-main/main" \
                || { echo "Abbruch: origin/main fehlt in $url." >&2; exit 2; }
            ref=refs/test-main/main
        else
            git fetch --quiet origin || echo "Warnung: git fetch ist fehlgeschlagen." >&2
            ref=origin/main
        fi
        git rev-parse --verify --quiet "$ref^{commit}" || { echo "Abbruch: $ref fehlt." >&2; exit 2; }
    }
    getestet() { grep -q "^$(git rev-parse "$1^{tree}") " "$STATE" 2> /dev/null; }
    m=$(main_holen) || exit 2
    if ! getestet "$m"; then
        mkdir -p "$LAUFEND"
        exec {main_fd}> "$LAUFEND/main.lock"
        if ! flock -n "$main_fd"; then
            echo "Ein anderer Lauf testet gerade main, warte auf ihn und hole main danach neu …"
            flock "$main_fd"
            m=$(main_holen) || exit 2
        fi
    fi
    if getestet "$m"; then
        echo "Alles grün: main $(git rev-parse --short "$m") ist schon getestet."
        exit 0
    fi
    echo "Teste den neuesten main: $(git rev-parse --short "$m")"
    # Die Sperre main.lock bleibt über exec bis zum Ende des Laufs gehalten
    set -- "$m"
fi

if [ "$#" -le 1 ] && [ "${TEST_ALLES:-0}" != 1 ] && [ "${BACKUP_TEST:-0}" != 1 ]; then
    c=$(git rev-parse --verify --quiet "${1:-HEAD}^{commit}" 2> /dev/null || true)
    if [ -n "$c" ] && teile_schon_gruen "$c"; then
        schon_gruen_vermerken "$c"
    fi
    # Kein Doppellauf: Prüft gerade ein anderer Lauf dasselbe Backend, wartet dieser Lauf auf
    # dessen Ergebnis, ohne einen Testplatz zu belegen. Die Sperre laufend/backend-<Schlüssel>.lock
    # bleibt über exec bis zum Ende des Laufs gehalten; ein abgebrochener Lauf gibt sie frei.
    # Das Frontend (~2 min) wartet nur, wenn das Backend nichts zu tun hat.
    if [ -n "$c" ] && [ -z "${TESTPLATZ:-}" ]; then
        mkdir -p "$LAUFEND"
        bk=$(teil_schluessel backend "$c")
        fk=$(teil_schluessel frontend "$c")
        if ! teil_gruen backend "$bk"; then
            exec {teil_b_fd}> "$LAUFEND/backend-$bk.lock"
            if ! flock -n "$teil_b_fd"; then
                echo "Ein anderer Lauf prüft gerade dasselbe Backend, warte auf sein Ergebnis …"
                flock "$teil_b_fd"
                if teile_schon_gruen "$c"; then schon_gruen_vermerken "$c"; fi
                teil_gruen backend "$bk" || echo "Der andere Lauf war nicht grün, prüfe selbst."
            fi
        fi
        if ! teil_gruen frontend "$fk"; then
            exec {teil_f_fd}> "$LAUFEND/frontend-$fk.lock"
            if ! flock -n "$teil_f_fd"; then
                if teil_gruen backend "$bk"; then
                    echo "Ein anderer Lauf prüft gerade dasselbe Frontend, warte auf sein Ergebnis …"
                    flock "$teil_f_fd"
                    if teile_schon_gruen "$c"; then schon_gruen_vermerken "$c"; fi
                else
                    exec {teil_f_fd}>&-
                fi
            fi
        fi
    fi
fi

if [ -z "${TESTPLATZ:-}" ]; then
    exec "$(dirname "$0")/testplatz.sh" "$0" "$@"
fi

REF="${1:-HEAD}"
shift || true
EIGENE_ARGS=$#

# Ergebnis immer eindeutig melden, auch wenn ein Aufrufer den Exit-Code nicht sieht
RESULT_OK=0
WORK=""
on_exit() {
    local rc=$?
    [ -n "$WORK" ] && cleanup
    if [ "$RESULT_OK" != 1 ]; then
        [ "$rc" -eq 0 ] && rc=1
        echo "FEHLGESCHLAGEN (Exit $rc): ${SHA:-$REF} ist nicht getestet." >&2
        exit "$rc"
    fi
}
trap on_exit EXIT

# Den Commit sicher auflösen. Eine volle SHA löst git rev-parse auch dann auf,
# wenn der Commit im Klon fehlt; deshalb mit --verify gegen ^{commit} prüfen.
resolve() { git rev-parse --verify --quiet "$REF^{commit}" 2> /dev/null || true; }
COMMIT=$(resolve)
if [ -z "$COMMIT" ]; then
    echo "$REF fehlt im Klon, hole von allen Remotes …"
    git fetch --all --quiet || echo "Warnung: git fetch ist fehlgeschlagen." >&2
    COMMIT=$(resolve)
fi
if [ -z "$COMMIT" ]; then
    echo "Abbruch: $REF ist auch nach git fetch nicht im Klon $(pwd)." >&2
    echo "In WSL holt der Klon vom Windows-Checkout: dort erst git fetch origin, dann erneut testen." >&2
    exit 2
fi
REF="$COMMIT"
SHA=$(git rev-parse --short "$COMMIT")
TREE=$(git rev-parse "$COMMIT^{tree}")

# Kerne vom Testplatz; alle Container laufen nur auf dessen Kernen
WORKERS="$TEST_KERNE"
CPUS="--cpuset-cpus=$TESTPLATZ_CPUS"
PYTEST_ARGS="${*:--q}"

ID="hubiplan-test-$(date +%s)-$$"
# Eigene Image-Namen je Lauf: zwei gleichzeitige Läufe dürfen sich nicht überschreiben
BACKEND_IMG="hubiplan-test-backend:$ID"
BACKUP_IMG="hubiplan-test-backup:$ID"
FE_PID=""
WORK=$(mktemp -d)
cleanup() {
    [ -n "$FE_PID" ] && kill "$FE_PID" 2> /dev/null && wait "$FE_PID" 2> /dev/null || true
    docker rm -f "$ID-fe" > /dev/null 2>&1 || true
    docker rm -f "$ID-db" > /dev/null 2>&1 || true
    docker network rm "$ID" > /dev/null 2>&1 || true
    docker volume rm "$ID-backups" > /dev/null 2>&1 || true
    docker volume rm "$ID-data" > /dev/null 2>&1 || true
    docker volume rm "$ID-seed-data" > /dev/null 2>&1 || true
    for suffix in rotation-data rotation-restore rotation-backups; do
        docker volume rm "$ID-$suffix" > /dev/null 2>&1 || true
    done
    # Dateien aus Containern ggf. mit deren Rechten entfernen
    rm -rf "$WORK" 2> /dev/null         || docker run --rm -v "$WORK:/w" node:24-alpine rm -rf /w/backend /w/frontend /w/deploy /w/scripts
    rm -rf "$WORK"
    docker image rm "$BACKEND_IMG" "$BACKUP_IMG" > /dev/null 2>&1 || true
}

B_KEY=$(teil_schluessel backend "$COMMIT")
F_KEY=$(teil_schluessel frontend "$COMMIT")
RUN_BACKEND=1
RUN_FRONTEND=1
if [ "$#" -eq 0 ] && [ "${TEST_ALLES:-0}" != 1 ]; then
    if teil_gruen backend "$B_KEY" && [ "${BACKUP_TEST:-0}" != 1 ]; then RUN_BACKEND=0; fi
    if teil_gruen frontend "$F_KEY"; then RUN_FRONTEND=0; fi
fi

echo "Teste $SHA ($(git log -1 --format=%s "$COMMIT")) lokal mit $WORKERS Kernen …"
[ "$RUN_BACKEND" = 1 ] || echo "Backend: dieser Inhalt war schon grün, wird nicht erneut geprüft"
[ "$RUN_FRONTEND" = 1 ] || echo "Frontend: dieser Inhalt war schon grün, wird nicht erneut geprüft"
git archive --format=tar "$REF" backend frontend deploy/backup | tar -x -C "$WORK"
start=$(date +%s)

# --- Frontend, Teil 1 (im Hintergrund, während das Backend sich vorbereitet) ---
# Installieren, Typprüfung, Lint und Formatierung hängen nicht an Zeitlimits. Die
# Vitest-Tests laufen danach allein, noch vor pytest: mit dem Backend zusammen auf
# denselben Kernen werden ihre Wartezeiten (findBy…) zu knapp.
fe_run() {
    docker run --rm --name "$ID-fe" "$CPUS" -v "$WORK/frontend:/app" -v "$WORK/backend:/backend:ro" \
        -v hubiplan-npm-cache:/root/.npm -w /app node:24-alpine sh -c "$1"
}
fe_checks() {
    fe_run "npm ci --no-audit --no-fund --loglevel=error > /dev/null \
        && npm run -s typecheck && npm run -s lint > /dev/null && npm run -s format:check > /dev/null \
        && npm run -s i18n:check" || return $?
    echo "Frontend: Typprüfung, Lint, Format ok"
}
if [ "$RUN_FRONTEND" = 1 ] && [ "${TEST_PARALLEL:-1}" = 1 ]; then
    fe_checks > "$WORK/frontend.log" 2>&1 &
    FE_PID=$!
fi

# Teil sofort als grün vermerken (nur volle Läufe ohne eigene pytest-Argumente)
teil_vermerken() {
    [ "$EIGENE_ARGS" -eq 0 ] || return 0
    mkdir -p "$(dirname "$PARTS")"
    echo "$1 $2 $SHA $(date -Iseconds)" >> "$PARTS"
}
# --- Frontend, Teil 2: auf Teil 1 warten, dann Vitest allein ---
FE_FEHLER=0
frontend_teil2() {
    [ "$RUN_FRONTEND" = 1 ] || return 0
    local rc=0 fstart
    fstart=$(date +%s)
    if [ -n "$FE_PID" ]; then
        wait "$FE_PID" || rc=$?
        FE_PID=""
        cat "$WORK/frontend.log"
    else
        fe_checks || rc=$?
    fi
    if [ "$rc" = 0 ]; then
        fe_run "npx vitest run --maxWorkers=$WORKERS --reporter=dot" || rc=$?
    fi
    if [ "$rc" != 0 ]; then
        echo "Frontend: FEHLGESCHLAGEN" >&2
        FE_FEHLER=$rc
        return 0
    fi
    echo "Frontend: ok ($(($(date +%s) - fstart)) s)"
    teil_vermerken frontend "$F_KEY"
}

# --- Backend ---
MIG_SKIP=0
if [ "$RUN_BACKEND" = 1 ]; then
    # Die Schichten mit den Abhängigkeiten nutzt Docker über die Läufe hinweg wieder
    docker build -q --build-arg REQUIREMENTS=requirements-dev.txt -t "$BACKEND_IMG" "$WORK/backend" > /dev/null
    docker network create "$ID" > /dev/null
    # Dasselbe festgeschriebene Datenbank-Image wie auf dem Server (docker-compose.server.yml)
    PG_IMAGE=$(git show "$REF:docker-compose.server.yml" | grep -m1 -oE 'image: postgres:[0-9][^ ]*' | cut -d' ' -f2)
    docker run -d --name "$ID-db" --network "$ID" "$CPUS" --tmpfs /var/lib/postgresql \
        -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=test \
        "$PG_IMAGE" -c max_connections=200 > /dev/null
    until docker exec "$ID-db" pg_isready -U test > /dev/null 2>&1; do sleep 1; done
    # App-Rolle vorab anlegen, damit parallele Test-Datenbanken nicht darum konkurrieren
    docker exec "$ID-db" psql -q -U test -d test -c \
        "CREATE ROLE hubiplan_app NOLOGIN NOSUPERUSER NOBYPASSRLS" > /dev/null

    docker run --rm "$CPUS" --entrypoint sh "$BACKEND_IMG" \
        -c "ruff check . && ruff format --check ."
    echo "Backend: ruff ok"
    # Bekannte Schwachstellen in den festgeschriebenen Python-Paketen (OSV/PyPI, braucht Netz).
    # Gesamtaudit 11.11., H-02. Überspringen nur bewusst: TEST_PIP_AUDIT=0
    if [ "${TEST_PIP_AUDIT:-1}" = 1 ]; then
        docker run --rm "$CPUS" --entrypoint sh "$BACKEND_IMG" \
            -c "pip-audit --progress-spinner off --disable-pip --require-hashes -r requirements-dev.txt"
        echo "Backend: pip-audit ok"
    fi
    # Fehlende oder widersprüchliche Migrationen (z. B. zwei parallel gemergte 0007 derselben
    # App) gleich hier melden, nach Sekunden statt am Ende des Laufs. Ohne Datenbank.
    if ! out=$(docker run --rm "$CPUS" -e PYTHONWARNINGS=ignore -e DJANGO_DEBUG=true \
        -e DJANGO_SECRET_KEY=nur-test -e DATABASE_URL=postgres://keine@127.0.0.1:1/keine \
        --entrypoint python "$BACKEND_IMG" manage.py makemigrations --check --dry-run 2>&1); then
        echo "$out" >&2
        echo "Backend: Migrationen fehlen oder widersprechen sich (makemigrations --check)" >&2
        exit 1
    fi
    echo "Backend: Migrationen vollständig und ohne Konflikt"
    # Übersetzung (konzepte/englisch.md): bis zur Abnahme nur Bericht, danach --streng
    docker run --rm "$CPUS" -e DJANGO_DEBUG=true -e DJANGO_SECRET_KEY=nur-test --entrypoint sh \
        "$BACKEND_IMG" -c "python manage.py uebersetzung_pruefen"

    # Webserver-Konfiguration (Caddy, nginx-Vorlagen für HestiaCP), aus dem geprüften Stand
    if git cat-file -e "$REF:scripts/pruefe-proxy.sh" 2> /dev/null; then
        git archive --format=tar "$REF" scripts/pruefe-proxy.sh deploy/web.Dockerfile deploy/Caddyfile \
            deploy/Caddyfile.proxy deploy/caddy deploy/hestia | tar -x -C "$WORK"
        "$WORK/scripts/pruefe-proxy.sh" "$WORK" "$CPUS"
    fi
    # Selbstupdate: Aktualisierer mit Wegwerf-Repository (braucht git und ssh-keygen)
    if git cat-file -e "$REF:scripts/pruefe-aktualisierer.sh" 2> /dev/null; then
        git archive --format=tar "$REF" scripts/pruefe-aktualisierer.sh deploy/aktualisierer \
            | tar -x -C "$WORK"
        "$WORK/scripts/pruefe-aktualisierer.sh" "$WORK"
    fi

    # Gemeinsamer Daten-Rückweg, nur mit Befehlsersatz und synthetischem Zielquellstand.
    if git cat-file -e "$REF:scripts/pruefe-daten-rueckweg.sh" 2> /dev/null; then
        git archive --format=tar "$REF" scripts/pruefe-daten-rueckweg.sh \
            deploy/daten-rueckweg.sh deploy/zurueck.sh deploy/server-setup.sh | tar -x -C "$WORK"
        sh "$WORK/scripts/pruefe-daten-rueckweg.sh" "$WORK"
    fi

    if git cat-file -e "$REF:scripts/pruefe-schluesselwechsel-betrieb.sh" 2> /dev/null; then
        git archive "$REF" scripts/pruefe-schluesselwechsel-betrieb.sh deploy/datenschluessel-wechseln.sh \
            deploy/server-setup.sh deploy/zurueck.sh deploy/deploy.sh | tar -x -C "$WORK"
        bash "$WORK/scripts/pruefe-schluesselwechsel-betrieb.sh" "$WORK"
    fi

    # Testdatenbank: einmal migrieren und je Worker kopieren (CREATE DATABASE … TEMPLATE, 0,2 s)
    # statt in jedem Worker alle Migrationen (je ~40 s Rechenzeit). Die migrierte Datenbank
    # wird als Vorlage zwischengespeichert. Ihr Schlüssel umfasst alles, was den Stand nach
    # migrate bestimmt: Migrationen, die von ihnen eingebundenen Module, Modelle, apps.py,
    # Einstellungen, Abhängigkeiten und das Datenbank-Image. TEST_DB_CACHE=0: ohne Vorlage.
    db_key() {
        local mods files
        # Module, die Migrationen einbinden (z. B. core.rls, exchange.models)
        mods=$(git grep -h -E '^(from|import) [a-z_]+\.[a-z_.]+' "$REF" -- 'backend/*/migrations/*.py' \
            | sed -E 's/^(from|import) ([a-z_.]+).*/\2/' | sort -u | sed 's#\.#/#g; s#^#backend/#; s#$#.py#')
        files=$(git ls-tree -r --name-only "$REF" -- backend \
            | grep -E '/migrations/|/models/|models[a-z_]*\.py$|/apps\.py$|^backend/config/settings\.py$|^backend/requirements' || true)
        { printf '%s\n' "$PG_IMAGE"; printf '%s\n' $mods $files | sort -u \
            | xargs git ls-tree "$REF" -- 2> /dev/null; } | sha256sum | cut -c1-16
    }
    if [ -d /mnt/e/tmp ]; then DB_CACHE_DEFAULT=/mnt/e/tmp/hubiplan-tests/db-vorlagen
    else DB_CACHE_DEFAULT="$HOME/.cache/hubiplan-test-db"; fi
    DB_CACHE="${TEST_DB_CACHE:-$DB_CACHE_DEFAULT}"
    TEST_DB=test_test   # so nennt pytest-django die Testdatenbank zu „test“, mit -n dann test_test_gwN
    docker exec "$ID-db" createdb -U test "$TEST_DB"
    dbstart=$(date +%s)
    DUMP=""
    if [ "$DB_CACHE" != 0 ]; then
        mkdir -p "$DB_CACHE"
        DUMP="$DB_CACHE/$(db_key).dump"
    fi
    if [ -n "$DUMP" ] && [ -s "$DUMP" ] && docker exec -i "$ID-db" pg_restore -U test -d "$TEST_DB" -1 < "$DUMP"; then
        echo "Backend: Testdatenbank aus der Vorlage ($(($(date +%s) - dbstart)) s)"
    else
        if [ -n "$DUMP" ] && [ -s "$DUMP" ]; then
            echo "Warnung: Vorlage $DUMP ließ sich nicht einspielen, migriere neu." >&2
            docker exec "$ID-db" dropdb -U test "$TEST_DB"
            docker exec "$ID-db" createdb -U test "$TEST_DB"
        fi
        docker run --rm --network "$ID" "$CPUS" \
            -e DJANGO_DEBUG=true -e DJANGO_SECRET_KEY=nur-test \
            -e DATABASE_URL="postgres://test:test@$ID-db:5432/$TEST_DB" \
            --entrypoint python "$BACKEND_IMG" manage.py migrate -v0
        if [ -n "$DUMP" ]; then
            # Erst fertig schreiben, dann umbenennen: ein paralleler Lauf liest nie eine halbe Datei
            docker exec "$ID-db" pg_dump -U test -Fc "$TEST_DB" > "$DUMP.$ID" && mv "$DUMP.$ID" "$DUMP"
            rm -f "$DUMP.$ID"
            # Nur die zehn neuesten Vorlagen behalten
            ls -1t "$DB_CACHE"/*.dump 2> /dev/null | tail -n +11 | xargs -r rm -f
        fi
        echo "Backend: Testdatenbank migriert ($(($(date +%s) - dbstart)) s)"
    fi
    for i in $(seq 0 $((WORKERS - 1))); do
        docker exec "$ID-db" psql -q -U test -d test -c \
            "CREATE DATABASE ${TEST_DB}_gw$i TEMPLATE $TEST_DB" > /dev/null
    done

    # Migrationstests (@pytest.mark.migration) migrieren hin und zurück und brauchen über ein
    # Drittel der Rechenzeit. Sie laufen nur, wenn ihr Schlüssel noch nicht grün war: der
    # Vorlagen-Schlüssel (Migrationen, Modelle, …), die markierten Testdateien, conftest.py,
    # factories.py und die Module, die diese Tests einbinden.
    mig_schluessel() {
        local tests mods
        tests=$(git grep -l 'mark\.migration' "$REF" -- 'backend/tests/test_*.py' | sed "s#^$REF:##" || true)
        mods=""
        if [ -n "$tests" ]; then
            # shellcheck disable=SC2086
            # „from a.b import c, d“ → a/b.py, a/b/__init__.py, a/b/c.py, a/b/c (Paket) …;
            # eingeklammerte Importlisten nehmen vorsichtshalber das ganze Paket a/b.
            mods=$(git grep -h -E '^(from|import) [a-z_]+' "$REF" -- $tests | awk '
                { m = $2; gsub(/\./, "/", m); print m ".py"; print m "/__init__.py" }
                $1 == "import" { print m }
                $1 == "from" && $4 ~ /^\(/ { print m }
                $1 == "from" && $4 !~ /^\(/ {
                    sub(/^from [^ ]+ import /, ""); n = split($0, teile, ",")
                    for (i = 1; i <= n; i++) {
                        split(teile[i], w, " "); if (w[1] == "") continue
                        print m "/" w[1] ".py"; print m "/" w[1]
                    }
                }' | sed 's#^#backend/#' | sort -u || true)
        fi
        # shellcheck disable=SC2086
        { db_key; printf '%s\n' $tests backend/tests/conftest.py backend/tests/factories.py $mods \
            | sort -u | xargs git ls-tree "$REF" -- 2> /dev/null; } | sha256sum | cut -c1-16
    }
    MIG_KEY=$(mig_schluessel)
    MIG_MARK=()
    if [ "$#" -eq 0 ] && [ "${TEST_ALLES:-0}" != 1 ] && teil_gruen migration "$MIG_KEY"; then
        MIG_SKIP=1
        MIG_MARK=(-m "not migration")
        echo "Backend: Migrationstests mit diesem Stand schon grün, werden ausgelassen"
    fi

    # Frontend zuerst fertig (Vitest allein, ~1,5 min), damit ein roter Frontend-Test nach
    # Minuten statt nach dem ganzen Backend auffällt.
    frontend_teil2

    # Vorlauf: Testdateien, die der Stand gegenüber main ändert, laufen zuerst (meist 1–2 min).
    # Scheitert einer, endet der Lauf gleich und gibt den Platz frei.
    VORLAUF=()
    IGNORE=()
    # TEST_VORLAUF_BASIS: andere Basis als main (z. B. zum Ausprobieren)
    basis=""
    for r in ${TEST_VORLAUF_BASIS:-} refs/test-main/main origin/main main; do
        basis=$(git merge-base "$COMMIT" "$r" 2> /dev/null) && break
        basis=""
    done
    if [ "$EIGENE_ARGS" -eq 0 ] && [ -n "$basis" ] && [ "$basis" != "$COMMIT" ]; then
        mapfile -t VORLAUF < <(git diff --name-only --diff-filter=AMR "$basis" "$COMMIT" -- 'backend/*test_*.py' \
            | sed 's#^backend/##')
        [ "${#VORLAUF[@]}" -le 30 ] || VORLAUF=()
    fi
    if [ "${#VORLAUF[@]}" -gt 0 ]; then
        vstart=$(date +%s)
        echo "Backend: Vorlauf mit ${#VORLAUF[@]} geänderten Testdatei(en) …"
        rc=0
        docker run --rm --network "$ID" "$CPUS" \
            -e DJANGO_DEBUG=true -e DJANGO_SECRET_KEY=nur-test \
            -e DATABASE_URL="postgres://test:test@$ID-db:5432/test" \
            -v "$WORK/deploy/backup/dateifelder.txt:/deploy/backup/dateifelder.txt:ro" \
            --entrypoint pytest "$BACKEND_IMG" -n "$WORKERS" --reuse-db --maxschedchunk=2 \
            -m "not migration" -q "${VORLAUF[@]}" || rc=$?
        # 5: alle Tests der Dateien sind Migrationstests, sie laufen im Hauptlauf
        if [ "$rc" != 0 ] && [ "$rc" != 5 ]; then
            echo "Backend: Vorlauf rot, Abbruch ohne Hauptlauf" >&2
            exit "$rc"
        fi
        echo "Backend: Vorlauf ok ($(($(date +%s) - vstart)) s)"
        # Frische Kopien für den Hauptlauf
        for i in $(seq 0 $((WORKERS - 1))); do
            docker exec "$ID-db" psql -q -U test -d test -c "DROP DATABASE IF EXISTS ${TEST_DB}_gw$i" \
                -c "CREATE DATABASE ${TEST_DB}_gw$i TEMPLATE $TEST_DB" > /dev/null
        done
        # Ohne Migrationstests sind die Dateien damit vollständig geprüft
        if [ "$MIG_SKIP" = 1 ] && [ "$rc" = 0 ]; then
            for f in "${VORLAUF[@]}"; do IGNORE+=("--ignore=$f"); done
        fi
    fi
    [ "$FE_FEHLER" = 0 ] || exit "$FE_FEHLER"

    # --reuse-db: die Kopien nehmen (migrate prüft nur noch, dass nichts fehlt).
    # --maxschedchunk=2: kleine Pakete, damit die langsamen Tests (zuerst gesammelt, siehe
    # tests/conftest.py) auf verschiedene Worker verteilt werden.
    docker run --rm --network "$ID" "$CPUS" \
        -e DJANGO_DEBUG=true -e DJANGO_SECRET_KEY=nur-test \
        -e DATABASE_URL="postgres://test:test@$ID-db:5432/test" \
        -v "$WORK/deploy/backup/dateifelder.txt:/deploy/backup/dateifelder.txt:ro" \
        --entrypoint pytest "$BACKEND_IMG" -n "$WORKERS" --reuse-db --maxschedchunk=2 \
        "${MIG_MARK[@]}" "${IGNORE[@]}" $PYTEST_ARGS
    echo "Backend: Tests ok ($(($(date +%s) - start)) s)"
    # Gleich vermerken: scheitert danach etwas anderes, läuft das Backend nicht noch einmal
    teil_vermerken backend "$B_KEY"
    [ "$MIG_SKIP" = 1 ] || teil_vermerken migration "$MIG_KEY"
else
    frontend_teil2
    [ "$FE_FEHLER" = 0 ] || exit "$FE_FEHLER"
fi

# --- Backup und Rücksicherung (optional) ---
if [ "${BACKUP_TEST:-0}" = "1" ]; then
    docker build -q -t "$BACKUP_IMG" "$WORK/deploy/backup" > /dev/null
    docker run --rm "$CPUS" -v "$WORK/deploy/backup/test_archive_check.py:/tmp/test_archive_check.py:ro" \
        --entrypoint python3 "$BACKUP_IMG" /tmp/test_archive_check.py
    docker run --rm --user 0 "$CPUS" --tmpfs /backups --tmpfs /tmp \
        -v "$WORK/deploy/backup/test-names.py:/tmp/test-names.py:ro" \
        --entrypoint python3 "$BACKUP_IMG" /tmp/test-names.py
    docker run --rm "$CPUS" --tmpfs /tmp -e BACKUP_HMAC_KEY=nur-ein-test \
        --entrypoint sh "$BACKUP_IMG" -c 'set -e
            mkdir /tmp/backups
            exec 9> /tmp/backups/.backup.lock; flock -n 9
            if BACKUP_DIR=/tmp/backups backup.sh > /dev/null 2>&1; then exit 1; fi
            test "$(find /tmp/backups -type f | wc -l)" = 1
            exec 9>&-
            flock -n /tmp/backups/.backup.lock true'
    echo "Backup: paralleler Starter abgewiesen, Sperre danach frei"
    # Synthetic source key: full local restoration must recover the exact bytes.
    printf '01234567890123456789012345678901' | base64 > "$WORK/test-data-key"
    chmod 644 "$WORK/test-data-key"
    docker volume create "$ID-seed-data" > /dev/null
    docker run --rm --user 0 "$CPUS" -v "$ID-seed-data:/data" --entrypoint sh "$BACKUP_IMG" \
        -c 'mkdir -p /data/media /data/private; chown -R 1000:1000 /data'
    docker exec "$ID-db" psql -q -U test -d test -c "CREATE DATABASE hubiplan" > /dev/null
    docker run --rm --network "$ID" "$CPUS" -e DJANGO_DEBUG=true \
        -e DJANGO_SECRET_KEY=nur-test -e DATABASE_URL="postgres://test:test@$ID-db:5432/hubiplan" \
        -v "$WORK/test-data-key:/run/secrets/datenschluessel:ro" \
        -e DATA_ENCRYPTION_KEY_FILE=/run/secrets/datenschluessel \
        -v "$ID-seed-data:/data" -e MEDIA_ROOT=/data/media -e PRIVATE_ROOT=/data/private \
        -v "$WORK/deploy/backup/test_application_restore.py:/tmp/test_application_restore.py:ro" \
        -e BACKUP_DB_PASSWORD=backup-nur-test \
        --entrypoint sh "$BACKEND_IMG" \
        -c "python manage.py migrate -v0 && python manage.py ensure_app_role > /dev/null && python manage.py seed_testdata --password Test-123456 > /dev/null && python /tmp/test_application_restore.py seed"
    docker volume create "$ID-backups" > /dev/null
    # Der Backup-Dienst läuft als Benutzer postgres (70)
    docker run --rm --user 0 -v "$ID-backups:/backups" --entrypoint chown         "$BACKUP_IMG" 70:70 /backups
    # Wie auf dem Server mit der Leserolle hubiplan_backup (GA8-06), nicht als Superuser
    docker run --rm --network "$ID" "$CPUS" -v "$ID-backups:/backups" \
        -e PGHOST="$ID-db" -e PGUSER=hubiplan_backup -e PGPASSWORD=backup-nur-test -e PGDATABASE=hubiplan \
        -e BACKUP_PASSPHRASE=nur-ein-test -e BACKUP_HMAC_KEY=nur-ein-test --entrypoint sh "$BACKUP_IMG" \
        -c "backup.sh > /dev/null && tail -1 /backups/restore-test.log"
    # Die Leserolle darf nichts ändern
    docker run --rm --network "$ID" "$CPUS" -e PGHOST="$ID-db" -e PGUSER=hubiplan_backup \
        -e PGPASSWORD=backup-nur-test -e PGDATABASE=hubiplan --entrypoint sh "$BACKUP_IMG" \
        -c 'set -e
            test "$(psql -tAc "SELECT count(*) > 0 FROM members_membership")" = t
            for sql in "DELETE FROM members_membership" "SET default_transaction_read_only = off; DELETE FROM members_membership" "CREATE TABLE fremd (x int)" "ALTER ROLE hubiplan_backup SUPERUSER"; do
                if psql -v ON_ERROR_STOP=1 -qc "$sql" > /dev/null 2>&1; then echo "Leserolle durfte: $sql" >&2; exit 1; fi
            done'
    echo "Backup: Leserolle sichert vollständig und darf nichts ändern"
    # hmac.sh rechnet ohne Schlüssel in der Befehlszeile, muss aber wie openssl rechnen
    docker run --rm "$CPUS" --tmpfs /tmp --entrypoint sh "$BACKUP_IMG" \
        -c 'set -e
            head -c 200000 /dev/urandom > /tmp/datei; : > /tmp/leer
            for key in nur-ein-test "$(head -c 32 /dev/urandom | od -An -tx1 | tr -d " \n")" \
                       "$(head -c 70 /dev/urandom | od -An -tx1 | tr -d " \n")"; do
                for f in /tmp/datei /tmp/leer; do
                    a=$(openssl dgst -sha256 -mac HMAC -macopt "key:$key" -r "$f" | cut -d" " -f1)
                    b=$(BACKUP_HMAC_KEY="$key" hmac.sh "$f")
                    [ "$a" = "$b" ] || { echo "hmac.sh weicht von openssl ab" >&2; exit 1; }
                done
            done'
    echo "Backup: hmac.sh stimmt mit openssl überein"
    # Ein abgebrochener Dump darf kein Backup hinterlassen und muss fehlschlagen
    docker run --rm --network "$ID" "$CPUS" -v "$ID-backups:/backups" \
        -e PGHOST="$ID-db" -e PGUSER=test -e PGPASSWORD=test -e PGDATABASE=gibt_es_nicht \
        -e BACKUP_PASSPHRASE=nur-ein-test -e BACKUP_HMAC_KEY=nur-ein-test --entrypoint sh "$BACKUP_IMG" \
        -c 'n=$(ls /backups/db_*.enc | wc -l)
            if backup.sh > /dev/null 2>&1; then echo "Backup trotz Fehler gemeldet" >&2; exit 1; fi
            [ "$(ls /backups/db_*.enc | wc -l)" = "$n" ] && ! ls /backups/*.tmp > /dev/null 2>&1'
    echo "Backup: abgebrochener Dump wird erkannt"
    # Eine veränderte Backup-Datei darf nicht eingespielt werden
    docker run --rm --network "$ID" "$CPUS" -v "$ID-backups:/backups" \
        -e BACKUP_PASSPHRASE=nur-ein-test -e BACKUP_HMAC_KEY=nur-ein-test \
        --entrypoint sh "$BACKUP_IMG" \
        -c 'f=$(ls -1t /backups/db_*.enc | head -1); printf x >> "$f"
            if restore-test.sh > /dev/null 2>&1; then echo "Verändertes Backup eingespielt" >&2; exit 1; fi'
    echo "Backup: veränderte Datei wird abgewiesen"
    # Mit öffentlichem Schlüssel: Server kann verschlüsseln, aber nicht lesen
    docker run --rm --network "$ID" "$CPUS" -v "$ID-backups:/backups" --tmpfs /tmp \
        -e PGHOST="$ID-db" -e PGUSER=test -e PGPASSWORD=test -e PGDATABASE=hubiplan \
        -e BACKUP_HMAC_KEY=nur-ein-test --entrypoint sh "$BACKUP_IMG" \
        -c 'set -e
            age-keygen -o /tmp/schluessel 2> /dev/null
            BACKUP_PUBLIC_KEY=$(age-keygen -y /tmp/schluessel) backup.sh > /dev/null
            f=$(ls -1t /backups/db_*.sql.gz.age | head -1)
            verify.sh "$f"
            tail -1 /backups/restore-test.log | grep -q "$(basename "$f")"
            age -d -i /tmp/schluessel "$f" | gunzip | tail -n 5 | grep -q "dump complete"
            age-keygen -o /tmp/fremd 2> /dev/null
            if age -d -i /tmp/fremd "$f" > /dev/null 2>&1; then echo "Fremder Schlüssel entschlüsselt" >&2; exit 1; fi
            if ls /backups/*.tmp /backups/*.sql.gz > /dev/null 2>&1; then echo "Klartext liegt herum" >&2; exit 1; fi'
    echo "Backup: öffentlicher Schlüssel, Rücksicherung vor dem Verschlüsseln"
    # Dateiliste: jede Datei, auf die die Datenbank zeigt, muss im Backup stehen
    docker volume create "$ID-data" > /dev/null
    docker run --rm --user 0 -v "$ID-data:/data" --entrypoint sh "$BACKUP_IMG" \
        -c 'mkdir -p /data/media/logos /data/private && printf logo > /data/media/logos/da.png
            chmod -R a+rX /data'
    docker exec "$ID-db" psql -q -U test -d hubiplan -c \
        "UPDATE organizations_organization SET logo = CASE
             WHEN id = (SELECT min(id) FROM organizations_organization) THEN 'logos/da.png'
             WHEN id = (SELECT id FROM organizations_organization ORDER BY id OFFSET 1 LIMIT 1) THEN 'logos/fehlt.png'
             ELSE '' END" > /dev/null
    for mode in age enc; do
        docker run --rm --network "$ID" "$CPUS" -v "$ID-backups:/backups" --tmpfs /tmp \
            -v "$ID-data:/data:ro" -v "$WORK/test-data-key:/run/secrets/datenschluessel:ro" -e MODE="$mode" \
            -e PGHOST="$ID-db" -e PGUSER=test -e PGPASSWORD=test -e PGDATABASE=hubiplan \
            -e BACKUP_PASSPHRASE=nur-ein-test -e BACKUP_HMAC_KEY=nur-ein-test --entrypoint sh "$BACKUP_IMG" \
            -c 'set -e
                fail() { echo "Dateiliste ($MODE): $1" >&2; tail -5 /backups/restore-test.log >&2; exit 1; }
                if [ "$MODE" = age ]; then
                    age-keygen -o /tmp/schluessel 2> /dev/null
                    BACKUP_PUBLIC_KEY=$(age-keygen -y /tmp/schluessel) backup.sh > /dev/null
                    l=$(ls -1t /backups/dateien_*.sha256.age | head -1)
                    verify.sh "$l"
                    age -d -i /tmp/schluessel "$l" > /tmp/liste
                else
                    backup.sh > /dev/null && restore-test.sh > /dev/null
                    l=$(ls -1t /backups/dateien_*.sha256.enc | head -1)
                    verify.sh "$l"
                    openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE -in "$l" > /tmp/liste
                fi
                grep -q "  ./media/logos/da.png$" /tmp/liste || fail "da.png fehlt in der Liste"
                (cd /data && sha256sum -c /tmp/liste > /dev/null) || fail "Prüfsummen passen nicht"
                # Letzter Lauf: Zeile „Rücksicherung ok … Dateien: …“ und davor seine Warnung
                tail -1 /backups/restore-test.log | grep -q "Dateien: 1 gesichert, .* Verweise" \
                    || fail "Zählung fehlt"
                block=$(awk "/WARNUNG: db_/ {b=\"\"} {b=b \$0 \"\n\"} END {printf \"%s\", b}" \
                    /backups/restore-test.log)
                echo "$block" | grep -q "^    ./media/logos/fehlt.png$" || fail "fehlt.png nicht gemeldet"
                if echo "$block" | grep -q "logos/da.png"; then fail "da.png fälschlich gemeldet"; fi
                grep -q "WARNUNG: .* Dateien fehlen" /backups/backup.log || fail "keine Warnung in backup.log"
                # Unvollständig: Merker für die Alarm-Mail, alte Backups bleiben (INF-F03)
                test -f /backups/.unvollstaendig || fail "Merker .unvollstaendig fehlt"
                grep -q "unvollständig, alte Backups bleiben" /backups/backup.log \
                    || fail "unvollständiges Backup hat alte Backups gelöscht"
'
    done
    echo "Backup: Dateiliste mit Prüfsummen, fehlende Dateien werden gemeldet"
    # Complete sets after the separate incomplete-reference checks above.
    docker run --rm --user 0 "$CPUS" -v "$ID-data:/data" -v "$ID-seed-data:/source:ro" \
        --entrypoint sh "$BACKUP_IMG" \
        -c 'cp -a /source/. /data/; printf recovered > /data/media/logos/fehlt.png; chmod -R a+rX /data'
    for mode in age enc; do
        docker run --rm --network "$ID" "$CPUS" --tmpfs /tmp -v "$ID-backups:/backups" \
            -v "$ID-data:/data:ro" -v "$WORK/test-data-key:/run/secrets/datenschluessel:ro" \
            -v "$WORK/deploy/backup/test-full-restore.sh:/tmp/test-full-restore.sh:ro" \
            -e MODE="$mode" -e PGHOST="$ID-db" -e PGUSER=test -e PGPASSWORD=test -e PGDATABASE=hubiplan \
            -e BACKUP_PASSPHRASE=nur-ein-test -e BACKUP_HMAC_KEY=nur-ein-test \
            --entrypoint sh "$BACKUP_IMG" /tmp/test-full-restore.sh
    done
    # Application-level probe: restore an independently decrypted SQL copy and use
    # the actually recovered snapshot key to decrypt real synthetic DB fields.
    docker exec "$ID-db" createdb -U test hubiplan_restore_probe
    docker run --rm "$CPUS" -v "$ID-backups:/backups" \
        -e BACKUP_PASSPHRASE=nur-ein-test -e BACKUP_HMAC_KEY=nur-ein-test \
        --entrypoint sh "$BACKUP_IMG" -c 'set -e; set -o pipefail
            d=$(cat /backups/test-probe-dump); verify.sh "$d"
            openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE -in "$d" | gunzip' \
        | docker exec -i "$ID-db" psql -q -U test -d hubiplan_restore_probe -v ON_ERROR_STOP=1 > /dev/null
    docker run --rm "$CPUS" -v "$ID-backups:/backups" \
        -e BACKUP_PASSPHRASE=nur-ein-test -e BACKUP_HMAC_KEY=nur-ein-test \
        --entrypoint sh "$BACKUP_IMG" -c 'set -e
            k=$(cat /backups/test-probe-key); verify.sh "$k"
            openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE -in "$k"' \
        > "$WORK/recovered-data-key"
    chmod 644 "$WORK/recovered-data-key" # synthetic key only, readable in backend container
    expected=$(docker run --rm --network "$ID" "$CPUS" -e DJANGO_DEBUG=true -e DJANGO_SECRET_KEY=nur-test \
        -v "$WORK/test-data-key:/run/secrets/datenschluessel:ro" -e DATA_ENCRYPTION_KEY_FILE=/run/secrets/datenschluessel \
        -e DATABASE_URL="postgres://test:test@$ID-db:5432/hubiplan" \
        -v "$WORK/deploy/backup/test_application_restore.py:/tmp/test_application_restore.py:ro" \
        --entrypoint python "$BACKEND_IMG" /tmp/test_application_restore.py fingerprint)
    actual=$(docker run --rm --network "$ID" "$CPUS" -e DJANGO_DEBUG=true -e DJANGO_SECRET_KEY=nur-test \
        -v "$WORK/recovered-data-key:/run/secrets/datenschluessel:ro" -e DATA_ENCRYPTION_KEY_FILE=/run/secrets/datenschluessel \
        -e DATABASE_URL="postgres://test:test@$ID-db:5432/hubiplan_restore_probe" \
        -v "$WORK/deploy/backup/test_application_restore.py:/tmp/test_application_restore.py:ro" \
        --entrypoint python "$BACKEND_IMG" /tmp/test_application_restore.py fingerprint)
    [ "$expected" = "$actual" ] || { echo "Restored encrypted fields differ" >&2; exit 1; }
    echo "Backup: Geburtsdaten und Rechnungs-/Rundschreibenkontakte mit wiederhergestelltem Satzschlüssel entschlüsselt"
    if git cat-file -e "$REF:scripts/pruefe-schluesselwechsel-restore.sh" 2> /dev/null; then
        git archive "$REF" scripts/pruefe-schluesselwechsel-restore.sh | tar -x -C "$WORK"
        source "$WORK/scripts/pruefe-schluesselwechsel-restore.sh"
    fi
    docker volume rm "$ID-data" > /dev/null
fi

if [ "$#" -gt 0 ]; then
    # Teil-Läufe (eigene pytest-Argumente) zählen nicht als Freigabe zum Ausrollen
    echo "Grün (Teil-Lauf, nicht als getestet vermerkt): $SHA"
    RESULT_OK=1
    exit 0
fi
mkdir -p "$(dirname "$STATE")"
jetzt=$(date -Iseconds)
vermerk=""
if [ "$RUN_BACKEND" = 0 ] || [ "$RUN_FRONTEND" = 0 ] || [ "$MIG_SKIP" = 1 ]; then vermerk=" teilweise"; fi
echo "$TREE $SHA $jetzt$vermerk" >> "$STATE"
echo "Alles grün: $SHA ist als getestet vermerkt ($(($(date +%s) - start)) s gesamt)."
RESULT_OK=1
