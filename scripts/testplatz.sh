#!/usr/bin/env bash
# testplatz: gemeinsame Testplätze für alle Projekte auf einem lokalen Arbeitsrechner.
#
#   testplatz [--kerne N] [--] Befehl [Argumente …]
#   testplatz --liste        belegte Plätze und Warteschlange anzeigen
#
# testplatz wartet auf einen freien Platz, bindet den Befehl an dessen Kerne und gibt
# ihm die Umgebungsvariablen
#   TESTPLATZ=1…n        belegter Platz
#   TEST_KERNE=N         so viele Kerne darf der Lauf nutzen (Worker, -n, --cpus …)
#   TESTPLATZ_CPUS=a-b   die Kerne des Platzes (für docker run --cpuset-cpus)
#
# Ohne Einstellung gibt es einen Platz mit allen Kernen. Wie viele Plätze und Kerne ein
# Rechner hat, steht lokal in ~/.config/testplatz (nicht im Repo), z. B.
#   PLAETZE=2
#   KERNE=4
# oder in den Umgebungsvariablen TESTPLATZ_PLAETZE und TESTPLATZ_KERNE.
# Ist TESTPLATZ schon gesetzt, läuft der Befehl direkt (verschachtelte Aufrufe).
# Die Plätze werden in der Reihenfolge der Anfragen vergeben (Warteschlange).
#
# Unter Linux/WSL hält es die Sperren selbst (~/.testplaetze/platz-N.lock). Unter Windows
# (Git Bash) holt es den Platz über WSL und lässt den Befehl unter Windows laufen, mit
# Prozessor-Affinität auf die Kerne des Platzes. Ältere Skripte mit der exklusiven Sperre
# ~/.hubiplan-tests.lock belegen alle Plätze: testplatz hält diese Datei geteilt.
#
# Installation (einmal, und nach Änderungen; immer beide, denn WSL findet über den
# Windows-PATH auch die Git-Bash-Kopie):
#   Linux/WSL: install -m 755 scripts/testplatz.sh ~/.local/bin/testplatz
#   Git Bash:  install -m 755 scripts/testplatz.sh ~/bin/testplatz
set -euo pipefail

PLAETZE=1
KERNE=
EINSTELLUNG="${TESTPLATZ_EINSTELLUNG:-${XDG_CONFIG_HOME:-$HOME/.config}/testplatz}"
# shellcheck disable=SC1090
[ -r "$EINSTELLUNG" ] && . "$EINSTELLUNG"
PLAETZE="${TESTPLATZ_PLAETZE:-$PLAETZE}"
MAX_KERNE="${TESTPLATZ_KERNE:-${KERNE:-$(nproc --all)}}"
WSL_DISTRO="${TESTPLATZ_DISTRO:-Debian}"

KERNE=$MAX_KERNE
WIN_DIR=""
LISTE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --kerne) KERNE="$2"; shift 2 ;;
        --windows) WIN_DIR="$2"; shift 2 ;;  # intern: vom Windows-Aufruf
        --liste) LISTE=1; shift ;;
        --) shift; break ;;
        *) break ;;
    esac
done
if [ "$LISTE" = 1 ]; then
    # Belegte Plätze und Warteschlange anzeigen (nur Linux/WSL)
    DIR="${TESTPLATZ_DIR:-$HOME/.testplaetze}"
    for p in $(seq 1 "$PLAETZE"); do
        if [ -e "$DIR/platz-$p.lock" ] && ! flock -n "$DIR/platz-$p.lock" true 2> /dev/null; then
            # .wer nur, wenn sein Prozess noch lebt (ältere Fassungen schreiben keine)
            wer=""
            if [ -r "$DIR/platz-$p.wer" ] && kill -0 "$(head -c 20 "$DIR/platz-$p.wer" | cut -d' ' -f1)" 2> /dev/null; then
                wer=$(tr '\n' ' ' < "$DIR/platz-$p.wer")
            fi
            echo "Platz $p belegt${wer:+: $wer}"
        else
            echo "Platz $p frei"
        fi
    done
    n=0
    for t in "$DIR/warteschlange"/*; do
        [ -e "$t" ] && kill -0 "${t##*-}" 2> /dev/null || continue
        n=$((n + 1))
        echo "wartet $n: $(tr '\n' ' ' < "$t")"
    done
    exit 0
fi
if [ $# -eq 0 ] && [ -z "$WIN_DIR" ]; then
    sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
fi
[ "$KERNE" -gt "$MAX_KERNE" ] && KERNE=$MAX_KERNE
[ "$KERNE" -lt 1 ] && KERNE=1

# Schon in einem Platz: nicht noch einen belegen
if [ -n "${TESTPLATZ:-}" ]; then
    [ "$KERNE" -gt "${TEST_KERNE:-$KERNE}" ] && KERNE=$TEST_KERNE
    export TEST_KERNE=$KERNE
    exec "$@"
fi

# --- Windows (Git Bash): Platz über WSL holen, Befehl unter Windows ausführen ---
if [ "$(uname -o 2> /dev/null)" = "Msys" ]; then
    TMPD="${TESTPLATZ_TMP:-${TMPDIR:-/tmp}/testplatz}"
    mkdir -p "$TMPD"
    SKRIPT="$TMPD/lauf-$$.sh"
    {
        echo 'set -e'
        # Affinität auf die Kerne des Platzes, Kindprozesse erben sie
        echo 'powershell.exe -NoProfile -Command "(Get-Process -Id $(cat /proc/$$/winpid)).ProcessorAffinity = $TESTPLATZ_MASKE" > /dev/null'
        printf 'cd %q\n' "$(pwd)"
        printf 'exec'; printf ' %q' "$@"; echo
    } > "$SKRIPT"
    rc=0
    MSYS_NO_PATHCONV=1 wsl.exe -d "$WSL_DISTRO" -e bash -lc \
        'exec testplatz --kerne "$1" --windows "$2"' _ "$KERNE" "$(cygpath -w "$SKRIPT")" || rc=$?
    rm -f "$SKRIPT"
    exit $rc
fi

# --- WSL/Linux: Platz belegen ---
DIR="${TESTPLATZ_DIR:-$HOME/.testplaetze}"
mkdir -p "$DIR"
ALT="${HUBIPLAN_TEST_LOCK:-$HOME/.hubiplan-tests.lock}"
exec {alt_fd}> "$ALT"
if ! flock -n -s "$alt_fd"; then
    # Blockierend warten, sonst kommt man zwischen alten Läufen nie dran
    echo "testplatz: ein älteres Testskript belegt alle Plätze, warte …" >&2
    flock -s "$alt_fd"
fi
# Warteschlange: Wer zuerst kommt, bekommt zuerst einen Platz. Jeder Wartende legt ein
# Ticket „<Nanosekunden>-<PID>“ ab; nur das älteste Ticket darf einen Platz nehmen. Tickets
# beendeter Prozesse räumt jeder Wartende weg, ein abgebrochener Lauf hält also niemanden auf.
Q="$DIR/warteschlange"
mkdir -p "$Q"
TICKET="$Q/$(date +%s%N)-$$"
printf '%s\n' "$(pwd)" "$*" > "$TICKET"
trap 'rm -f "$TICKET"' EXIT
platz_nehmen() {
    local p
    for p in $(seq 1 "$PLAETZE"); do
        exec {fd}> "$DIR/platz-$p.lock"
        if flock -n "$fd"; then
            PLATZ=$p
            return 0
        fi
        exec {fd}>&-
    done
    return 1
}
gemeldet=""
while :; do
    vorne=0
    for t in "$Q"/*; do
        [ -e "$t" ] || continue
        [ "$t" = "$TICKET" ] && break
        if kill -0 "${t##*-}" 2> /dev/null; then vorne=$((vorne + 1)); else rm -f "$t"; fi
    done
    if [ "$vorne" = 0 ] && platz_nehmen; then
        break
    fi
    if [ "$gemeldet" != "$vorne" ]; then
        if [ "$vorne" = 0 ]; then
            echo "testplatz: alle $PLAETZE Plätze belegt, als Nächster an der Reihe …" >&2
        else
            echo "testplatz: alle $PLAETZE Plätze belegt, $vorne Lauf/Läufe vor diesem in der Warteschlange …" >&2
        fi
        gemeldet=$vorne
    fi
    sleep 2
done
rm -f "$TICKET"
trap - EXIT
# Wer den Platz hat (für testplatz --liste)
printf '%s\n' "$$ $(date -Iseconds)" "$(pwd)" "$*" > "$DIR/platz-$PLATZ.wer"

# Kerne des Platzes: nebeneinander ab Kern 0 (bei 6 Kernen: Platz 1 0–5, Platz 2 6–11 …).
# Reichen die Kerne nicht, rückt der Platz ans Ende und teilt sich Kerne mit dem vorigen.
N=$(nproc --all)
[ "$MAX_KERNE" -gt "$N" ] && MAX_KERNE=$N
[ "$KERNE" -gt "$N" ] && KERNE=$N
start=$(( (PLATZ - 1) * MAX_KERNE ))
[ $((start + KERNE)) -gt "$N" ] && start=$((N - KERNE))
CPUS="$start-$((start + KERNE - 1))"
export TESTPLATZ=$PLATZ TEST_KERNE=$KERNE TESTPLATZ_CPUS=$CPUS
# Ein älteres Testskript im Platz würde ~/.hubiplan-tests.lock exklusiv sperren wollen,
# das testplatz selbst geteilt hält, und auf sich selbst warten. Es bekommt deshalb
# eine eigene Sperrdatei für diesen Platz.
export HUBIPLAN_TEST_LOCK="$DIR/innen-$PLATZ.lock"
echo "testplatz: Platz $PLATZ, $KERNE Kerne ($CPUS)" >&2

if [ -n "$WIN_DIR" ]; then
    # Windows-Kerne: ebenfalls nebeneinander ab Kern 0
    start=$(( (PLATZ - 1) * MAX_KERNE ))
    export TESTPLATZ_MASKE=$(( ((1 << KERNE) - 1) << start ))
    export WSLENV="TESTPLATZ:TEST_KERNE:TESTPLATZ_CPUS:TESTPLATZ_MASKE${WSLENV:+:$WSLENV}"
    exec "/mnt/c/Program Files/Git/bin/bash.exe" "$WIN_DIR"
fi
exec taskset -c "$CPUS" "$@"
