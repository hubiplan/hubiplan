#!/usr/bin/env bash
# testplatz: gemeinsame Testplätze für alle Projekte auf einem lokalen Arbeitsrechner.
#
#   testplatz [--kerne N] [--zug] [--] Befehl [Argumente …]
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
# Plätze verschiedener Größe: PLATZ_KERNE="12 6" (Kerne je Platz, PLAETZE ergibt sich).
# ZUG_PLATZ=1 behält Platz 1 dem Merge-Zug vor (scripts/zug.sh, Aufruf mit --zug); alle
# anderen Läufe nehmen die übrigen Plätze. Ohne ZUG_PLATZ nimmt --zug einen beliebigen Platz.
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
# Kerne je Platz (PLATZ_KERNE="12 6"); sonst alle Plätze gleich groß
read -r -a GROESSEN <<< "${TESTPLATZ_PLATZ_KERNE:-${PLATZ_KERNE:-}}"
if [ "${#GROESSEN[@]}" -gt 0 ]; then
    PLAETZE=${#GROESSEN[@]}
    MAX_KERNE=0
    for g in "${GROESSEN[@]}"; do [ "$g" -gt "$MAX_KERNE" ] && MAX_KERNE=$g; done
else
    for _ in $(seq 1 "$PLAETZE"); do GROESSEN+=("$MAX_KERNE"); done
fi
ZUG_PLATZ="${TESTPLATZ_ZUG_PLATZ:-${ZUG_PLATZ:-}}"
platz_groesse() { echo "${GROESSEN[$(($1 - 1))]}"; }
# Erster Kern eines Platzes: Summe der Plätze davor
platz_start() {
    local i s=0
    for ((i = 1; i < $1; i++)); do s=$((s + $(platz_groesse "$i"))); done
    echo "$s"
}

KERNE=""
ZUG=0
WIN_DIR=""
LISTE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --kerne) KERNE="$2"; shift 2 ;;
        --zug) ZUG=1; shift ;;
        --windows) WIN_DIR="$2"; shift 2 ;;  # intern: vom Windows-Aufruf
        --liste) LISTE=1; shift ;;
        --) shift; break ;;
        *) break ;;
    esac
done
if [ "$LISTE" = 1 ]; then
    # Belegte Plätze und Warteschlange anzeigen. Unter Windows liegen sie in WSL.
    if [ "$(uname -o 2> /dev/null)" = "Msys" ]; then
        exec wsl.exe -d "$WSL_DISTRO" -e bash -lc 'exec testplatz --liste'
    fi
    DIR="${TESTPLATZ_DIR:-$HOME/.testplaetze}"
    for p in $(seq 1 "$PLAETZE"); do
        if [ -e "$DIR/platz-$p.lock" ] && ! flock -n "$DIR/platz-$p.lock" true 2> /dev/null; then
            # .wer nur, wenn sein Prozess noch lebt (ältere Fassungen schreiben keine)
            wer=""
            if [ -r "$DIR/platz-$p.wer" ] && kill -0 "$(head -c 20 "$DIR/platz-$p.wer" | cut -d' ' -f1)" 2> /dev/null; then
                wer=$(tr '\n' ' ' < "$DIR/platz-$p.wer")
            fi
            echo "Platz $p ($(platz_groesse "$p") Kerne${ZUG_PLATZ:+$([ "$p" = "$ZUG_PLATZ" ] && echo ", Zug")}) belegt${wer:+: $wer}"
        else
            echo "Platz $p ($(platz_groesse "$p") Kerne${ZUG_PLATZ:+$([ "$p" = "$ZUG_PLATZ" ] && echo ", Zug")}) frei"
        fi
    done
    for q in warteschlange warteschlange-zug; do
        n=0
        for t in "$DIR/$q"/*; do
            [ -e "$t" ] && kill -0 "${t##*-}" 2> /dev/null || continue
            n=$((n + 1))
            echo "wartet${q#warteschlange} $n: $(tr '\n' ' ' < "$t")"
        done
    done
    exit 0
fi
if [ $# -eq 0 ] && [ -z "$WIN_DIR" ]; then
    sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
fi
if [ -n "$KERNE" ]; then
    [ "$KERNE" -gt "$MAX_KERNE" ] && KERNE=$MAX_KERNE
    [ "$KERNE" -lt 1 ] && KERNE=1
fi

# Schon in einem Platz: nicht noch einen belegen
if [ -n "${TESTPLATZ:-}" ]; then
    [ -z "$KERNE" ] && KERNE=${TEST_KERNE:-$MAX_KERNE}
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
    zugarg=""
    [ "$ZUG" = 1 ] && zugarg="--zug"
    MSYS_NO_PATHCONV=1 wsl.exe -d "$WSL_DISTRO" -e bash -lc \
        'exec testplatz ${1:+--kerne "$1"} $3 --windows "$2"' _ "$KERNE" "$(cygpath -w "$SKRIPT")" "$zugarg" || rc=$?
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
# Der Zug hat eine eigene Warteschlange für seinen Platz, alle anderen eine gemeinsame.
Q="$DIR/warteschlange"
[ "$ZUG" = 1 ] && [ -n "$ZUG_PLATZ" ] && Q="$DIR/warteschlange-zug"
mkdir -p "$Q"
TICKET="$Q/$(date +%s%N)-$$"
printf '%s\n' "$(pwd)" "$*" > "$TICKET"
trap 'rm -f "$TICKET"' EXIT
platz_nehmen() {
    local p
    for p in $(seq 1 "$PLAETZE"); do
        # Der Zug-Platz nur für den Zug, der Zug nur auf seinem Platz
        if [ -n "$ZUG_PLATZ" ] && [ "$PLAETZE" -gt 1 ]; then
            if [ "$ZUG" = 1 ]; then [ "$p" = "$ZUG_PLATZ" ] || continue
            else [ "$p" = "$ZUG_PLATZ" ] && continue; fi
        fi
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

# Kerne des Platzes: nebeneinander ab Kern 0 (bei 6 Kernen: Platz 1 0–5, Platz 2 6–11 …;
# bei PLATZ_KERNE="12 6": Platz 1 0–11, Platz 2 12–17). Reichen die Kerne nicht, rückt der
# Platz ans Ende und teilt sich Kerne mit dem vorigen.
N=$(nproc --all)
GROESSE=$(platz_groesse "$PLATZ")
[ -z "$KERNE" ] || [ "$KERNE" -gt "$GROESSE" ] && KERNE=$GROESSE
[ "$KERNE" -gt "$N" ] && KERNE=$N
start=$(platz_start "$PLATZ")
win_start=$start
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
    export TESTPLATZ_MASKE=$(( ((1 << KERNE) - 1) << win_start ))
    export WSLENV="TESTPLATZ:TEST_KERNE:TESTPLATZ_CPUS:TESTPLATZ_MASKE${WSLENV:+:$WSLENV}"
    exec "/mnt/c/Program Files/Git/bin/bash.exe" "$WIN_DIR"
fi
exec taskset -c "$CPUS" "$@"
