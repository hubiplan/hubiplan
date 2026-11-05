#!/usr/bin/env bash
# Lokale Befehlsersatz-Tests des Betriebsablaufs; keine Dienste oder Serverzugriffe.
set -euo pipefail
ROOT=$1
TEST_ROOT=$(mktemp -d)
trap 'rm -rf "$TEST_ROOT"' EXIT
mkdir -p "$TEST_ROOT/bin"
export PATH="$TEST_ROOT/bin:$PATH"
cat > "$TEST_ROOT/bin/docker" <<'MOCK'
#!/usr/bin/env bash
set -eu
printf '%q ' "$@" >> "$CASE/log"; printf '\n' >> "$CASE/log"
while [ "$#" -gt 0 ] && [[ ! "$1" =~ ^(run|stop|ps|up)$ ]]; do shift; done
CMD=$1; shift
case "$CMD" in
    stop) [ "${FAIL:-}" != stop ]; exit $? ;;
    ps)
        [ "${FAIL:-}" != ps_error ] || exit 1
        [ "${FAIL:-}" != active ] || echo active-container; exit 0 ;;
    up)
        if [ "${FAIL:-}" = restart ] && [ "${!#}" = backend ]; then exit 1; fi
        exit 0 ;;
esac
ARGS=" $* "
if [[ "$ARGS" == *" datenschluessel_ausmustern "* ]]; then
    if [[ "$ARGS" == *" --probe "* ]]; then
        [ ! -e "$CASE/retired" ] && [ "${FAIL:-}" != stale ]
    else
        [ -e "$CASE/retired" ] || echo entfernt >> "$CASE/material-removals"
        touch "$CASE/retired"
        [ "${FAIL:-}" != retirement ]
    fi
elif [[ "$ARGS" == *" datenschluessel_wechseln "* ]]; then
    if [[ "$ARGS" == *" --status "* ]]; then
        count=$(cat "$CASE/status-count" 2>/dev/null || echo 0)
        count=$((count + 1)); echo "$count" > "$CASE/status-count"
        [ ! -e "$CASE/current" ] && echo '0 none' || cat "$CASE/current"
        if [ "${FAIL:-}" = status_after ] && [ "$count" -gt 1 ]; then exit 1; fi
    elif [[ "$ARGS" == *" --probe "* ]]; then
        [ "${FAIL:-}" != probe ]
    elif [[ "$ARGS" == *" --pruefen "* ]]; then
        [ "${FAIL:-}" != verify ]
    elif [[ "$ARGS" == *" --starten "* ]]; then
        echo '1 running' > "$CASE/current"
        [ "${FAIL:-}" != rotation ] || exit 1
        echo '1 completed' > "$CASE/current"
    else
        echo '1 completed' > "$CASE/current"
    fi
elif [[ "$ARGS" == *" --entrypoint backup-receipt.sh "* ]]; then
    NAME=${!#}
    [ "${FAIL:-}" != receipt ] || exit 1
    cat "$CASE/$NAME"
elif [[ "$ARGS" == *" --entrypoint backup.sh "* ]]; then
    NAME=
    for arg in "$@"; do
        case "$arg" in BACKUP_RECEIPT_NAME=*) NAME=${arg#*=};; esac
    done
    [ -n "$NAME" ]
    if [[ "$NAME" == *-vorher ]]; then
        [ "${FAIL:-}" != backup_before ] || exit 1
        echo '2026-11-05_010101_aaaaaaaaaaaa' > "$CASE/$NAME"
    else
        [ "${FAIL:-}" != backup_after ] || exit 1
        echo '2026-11-05_010102_bbbbbbbbbbbb' > "$CASE/$NAME"
    fi
else
    echo 'Unerwarteter Betriebsbefehl' >&2; exit 1
fi
MOCK
chmod +x "$TEST_ROOT/bin/docker"
for fault in ok stop active ps_error status_after backup_before probe rotation verify backup_after receipt restart; do
    CASE="$TEST_ROOT/$fault mit Leerzeichen"
    export CASE FAIL=$fault
    mkdir -p "$CASE/app"
    printf 'COMPOSE_PROJECT_NAME=testablauf\n' > "$CASE/app/.env"
    printf '%040d\n' 1 > "$CASE/app/.fassung"
    touch "$CASE/app/docker-compose.server.yml" "$CASE/log"
    if (cd "$CASE/app" && bash "$ROOT/deploy/datenschluessel-wechseln.sh" --organisation 42 --starten > "$CASE/output" 2>&1); then
        [ "$fault" = ok ]
        [ ! -e "$CASE/app.datenschluesselwechsel/status" ]
    else
        [ "$fault" != ok ] || { cat "$CASE/output" >&2; exit 1; }
        [ -f "$CASE/app.datenschluesselwechsel/status" ]
        if [ "$fault" != restart ]; then ! grep -q ' up ' "$CASE/log"; fi
        # Direkter Setup-/Rückweg darf die Schreibpause nicht aufheben.
        for helper in server-setup.sh zurueck.sh; do
            if (cd "$CASE/app" && ZIEL="$CASE/app" sh "$ROOT/deploy/$helper" > /dev/null 2>&1); then exit 1; fi
        done
        FAIL=ok
        export FAIL
        (cd "$CASE/app" && bash "$ROOT/deploy/datenschluessel-wechseln.sh" --organisation 42 --fortsetzen > "$CASE/resume" 2>&1) || { cat "$CASE/resume" >&2; exit 1; }
        [ ! -e "$CASE/app.datenschluesselwechsel/status" ]
    fi
    [ ! -d "$CASE/app.sperre" ]
    [ "$(grep -c -- ' --starten ' "$CASE/log")" = 1 ]
    grep -q 'BACKUP_REQUIRE_COMPLETE=1' "$CASE/log"
    grep -q 'BACKUP_PRESERVE_EXISTING=1' "$CASE/log"
    grep -q 'up -d --no-deps --wait --wait-timeout 300 worker beat backup' "$CASE/log"
done
# Konkurrierendes Deploy: keine Dienste verändern, vorhandene Sperre erhalten.
mkdir "$CASE/app.sperre"
before=$(wc -l < "$CASE/log")
if (cd "$CASE/app" && bash "$ROOT/deploy/datenschluessel-wechseln.sh" --organisation 42 --starten > /dev/null 2>&1); then exit 1; fi
[ "$(wc -l < "$CASE/log")" = "$before" ]
for helper in server-setup.sh zurueck.sh; do
    if (cd "$CASE/app" && ZIEL="$CASE/app" sh "$ROOT/deploy/$helper" > /dev/null 2>&1); then exit 1; fi
done
[ "$(wc -l < "$CASE/log")" = "$before" ]
rmdir "$CASE/app.sperre"
mkdir "$CASE/app.datenschluesselwechsel/offen"
for helper in server-setup.sh zurueck.sh; do
    if (cd "$CASE/app" && ZIEL="$CASE/app" sh "$ROOT/deploy/$helper" > /dev/null 2>&1); then exit 1; fi
done
rmdir "$CASE/app.datenschluesselwechsel/offen"

# Früher gestartetes deploy.sh: Zielquellstand und bereits gehaltene Sperre passen
# zusammen. Nur den tatsächlichen Setup-Vorspann ausführen, keine Installation.
awk '/^# Beim ersten Mal:/{exit} {print}' "$ROOT/deploy/server-setup.sh" > "$CASE/setup-prefix.sh"
printf '\n[ -d "$ZIEL.sperre" ]\n' >> "$CASE/setup-prefix.sh"
(cd "$CASE/app" && ZIEL="$CASE/app" sh "$CASE/setup-prefix.sh")
[ ! -d "$CASE/app.sperre" ]
mkdir "$CASE/app.neu" "$CASE/app.sperre"
cp "$CASE/app/.fassung" "$CASE/app.neu/.fassung"
short=$(cut -c1-8 "$CASE/app/.fassung")
printf '%s testcaller\n' "$short" > "$CASE/app.sperre/lauf"
(cd "$CASE/app.neu" && ZIEL="$CASE/app" sh "$CASE/setup-prefix.sh")
[ -d "$CASE/app.sperre" ]
printf 'ffffffff anderer-stand\n' > "$CASE/app.sperre/lauf"
if (cd "$CASE/app.neu" && ZIEL="$CASE/app" sh "$CASE/setup-prefix.sh" > /dev/null 2>&1); then exit 1; fi
rm "$CASE/app.sperre/lauf"
rmdir "$CASE/app.sperre"

# Nach Aktivierung darf ein verlorener Vorher-Nachweis nicht ersetzt/übergangen werden.
CASE="$TEST_ROOT/verlorener-nachweis"
export CASE FAIL=rotation
mkdir -p "$CASE/app"
printf 'COMPOSE_PROJECT_NAME=testablauf\n' > "$CASE/app/.env"
printf '%040d\n' 1 > "$CASE/app/.fassung"
touch "$CASE/app/docker-compose.server.yml" "$CASE/log"
if (cd "$CASE/app" && bash "$ROOT/deploy/datenschluessel-wechseln.sh" --organisation 42 --starten > /dev/null 2>&1); then exit 1; fi
token=$(sed -n 's/^token=//p' "$CASE/app.datenschluesselwechsel/status")
mv "$CASE/$token-vorher" "$CASE/gespeicherter-nachweis"
export FAIL=ok
if (cd "$CASE/app" && bash "$ROOT/deploy/datenschluessel-wechseln.sh" --organisation 42 --fortsetzen > /dev/null 2>&1); then exit 1; fi
[ -f "$CASE/app.datenschluesselwechsel/status" ]
! grep -q ' up ' "$CASE/log"
mv "$CASE/gespeicherter-nachweis" "$CASE/$token-vorher"
(cd "$CASE/app" && bash "$ROOT/deploy/datenschluessel-wechseln.sh" --organisation 42 --fortsetzen > /dev/null)
[ "$(grep -c -- ' --starten ' "$CASE/log")" = 1 ]
grep -Fq 'test ! -e '\''$DIR.datenschluesselwechsel/status' "$ROOT/deploy/deploy.sh"
# Ausmusterung nutzt dieselbe Schreibpause, Nachweise und Deploy-Sperren. Nach
# einem Abbruch nach Materialentfernung muss die unveränderte Freigabe fortsetzen.
for fault in ok stop ps_error stale backup_before retirement verify backup_after receipt restart; do
    CASE="$TEST_ROOT/ausmustern-$fault"
    export CASE FAIL=$fault
    mkdir -p "$CASE/app"
    printf 'COMPOSE_PROJECT_NAME=testablauf\n' > "$CASE/app/.env"
    printf '%040d\n' 1 > "$CASE/app/.fassung"
    touch "$CASE/app/docker-compose.server.yml" "$CASE/log"
    echo '1 completed' > "$CASE/current"
    proof=$(printf 'a%.0s' {1..64})
    if (cd "$CASE/app" && bash "$ROOT/deploy/datenschluessel-wechseln.sh" --organisation 42 --starten \
        --ausmustern 17 --pruefsumme "$proof" --freigabe TEST-42 --sicherungen-geprueft > "$CASE/output" 2>&1); then
        [ "$fault" = ok ]
    else
        [ "$fault" != ok ] || { cat "$CASE/output" >&2; exit 1; }
        [ -f "$CASE/app.datenschluesselwechsel/status" ]
        for helper in server-setup.sh zurueck.sh; do
            if (cd "$CASE/app" && ZIEL="$CASE/app" sh "$ROOT/deploy/$helper" > /dev/null 2>&1); then exit 1; fi
        done
        if [ "$fault" = backup_after ]; then
            token=$(sed -n 's/^token=//p' "$CASE/app.datenschluesselwechsel/status")
            mv "$CASE/$token-vorher" "$CASE/beleg"
            FAIL=ok; export FAIL
            if (cd "$CASE/app" && bash "$ROOT/deploy/datenschluessel-wechseln.sh" --organisation 42 --fortsetzen > /dev/null 2>&1); then exit 1; fi
            mv "$CASE/beleg" "$CASE/$token-vorher"
        fi
        FAIL=ok; export FAIL
        if [ "$fault" = retirement ]; then
            # Nach Entfernung darf eine andere Freigabe nicht übernommen werden.
            if (cd "$CASE/app" && bash "$ROOT/deploy/datenschluessel-wechseln.sh" --organisation 42 --fortsetzen \
                --pruefsumme "$(printf 'b%.0s' {1..64})" --freigabe TEST-43 --sicherungen-geprueft > /dev/null 2>&1); then exit 1; fi
            grep -q '^approval=TEST-42$' "$CASE/app.datenschluesselwechsel/status"
        fi
        if [ "$fault" = stale ]; then
            (cd "$CASE/app" && bash "$ROOT/deploy/datenschluessel-wechseln.sh" --organisation 42 --fortsetzen \
                --pruefsumme "$(printf 'b%.0s' {1..64})" --freigabe TEST-43 --sicherungen-geprueft > "$CASE/resume" 2>&1) || { cat "$CASE/resume" >&2; exit 1; }
            grep -q '^approval=TEST-43$' "$CASE/app.datenschluesselwechsel/letzter-abschluss"
        else
            (cd "$CASE/app" && bash "$ROOT/deploy/datenschluessel-wechseln.sh" --organisation 42 --fortsetzen > "$CASE/resume" 2>&1) || { cat "$CASE/resume" >&2; exit 1; }
        fi
    fi
    [ ! -e "$CASE/app.datenschluesselwechsel/status" ]
    [ "$(wc -l < "$CASE/material-removals")" = 1 ]
    ! grep -q -- ' --starten ' "$CASE/log"
    grep -q -- "--schluessel 17 --pruefsumme $proof --freigabe TEST-42" "$CASE/log"
    grep -q 'BACKUP_PRESERVE_EXISTING=1' "$CASE/log"
done

bash -n "$ROOT/deploy/datenschluessel-wechseln.sh"
echo "Schlüsselwechsel-Betrieb: Sicherungssätze, Schreibpause, Fehlerpfade, Wiederaufnahme und Neustartsperren ok"
