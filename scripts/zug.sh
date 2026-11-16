#!/usr/bin/env bash
# Merge-Zug (docs/testserver.md, „Merge-Zug“): PRs nacheinander gegen den aktuellen main testen.
#
#   scripts/zug.sh <PR-Nummer>     PR einreihen, testen; bei Grün sagt der Zug, was jetzt zu mergen ist
#   scripts/zug.sh --status        wer im Zug wartet, was gerade läuft, worauf der Zug wartet
#   scripts/zug.sh --fertig        warten, bis der zuletzt grün gemeldete Stand in main ist
#
# Ablauf: Der PR wird vorgeprüft (scripts/vorpruefung.sh) und reiht sich für den Zug-Platz ein
# (testplatz --zug). Ist er dran, mischt der Zug ihn lokal auf den neuesten main und testet genau
# diesen Stand mit scripts/test.sh. Warten weitere PRs, fahren bis zu ZUG_BUENDEL (3) zusammen;
# ein PR mit Migrationen fährt allein. Bei Grün ist der Tree als getestet vermerkt, und der Zug
# hält seinen Platz, bis der Stand in main angekommen ist (höchstens ZUG_WARTEN Sekunden, 1800):
# In dieser Zeit mergt der Thread, der den Lauf gestartet hat, die genannten PRs in der genannten
# Reihenfolge auf GitHub („Create a merge commit“). Weil main sich dazwischen nicht bewegt, hat
# der neue main genau den getesteten Tree: kein Nachtest, kein eigener main-Lauf, ausrollbar.
# Rot oder Mischkonflikt: der PR fliegt raus, der Zug fährt weiter.
set -euo pipefail

HIER="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="$(dirname "${HUBIPLAN_TESTED_FILE:-$HOME/.local/state/hubiplan/tested-trees}")"
ZUG="${ZUG_DIR:-$STATE_DIR/zug}"
ANFRAGEN="$ZUG/anfragen"
BUENDEL="${ZUG_BUENDEL:-3}"
WARTEN="${ZUG_WARTEN:-1800}"
TEST="${ZUG_TEST:-$HIER/test.sh}"
mkdir -p "$ANFRAGEN"

wert() { sed -n "s/^$2=//p" "$1" 2> /dev/null | tail -1; }
lebt() { kill -0 "$1" 2> /dev/null; }

# Von GitHub holen. In WSL ist origin oft der Windows-Klon (ein Pfad): dort von GitHub holen und
# von dort übernehmen. $1 Ref auf GitHub, $2 lokaler Ref.
holen() {
    local url
    url=$(git remote get-url origin 2> /dev/null || true)
    if [ -d "$url" ] && git -C "$url" remote get-url origin > /dev/null 2>&1; then
        git -C "$url" fetch --quiet origin "+$1:$2" || return 1
        git fetch --quiet origin "+$2:$2"
    else
        git fetch --quiet origin "+$1:$2"
    fi
}
main_holen() {
    if [ -n "${ZUG_MAIN_REF:-}" ]; then
        git rev-parse --verify --quiet "$ZUG_MAIN_REF^{commit}"
        return
    fi
    holen refs/heads/main refs/zug/main > /dev/null || { echo "Zug: main ließ sich nicht holen." >&2; return 1; }
    git rev-parse refs/zug/main
}
tree() { git rev-parse "$1^{tree}"; }

# --- Anzeige ---
if [ "${1:-}" = "--status" ]; then
    for f in "$ZUG"/halten-*; do
        [ -e "$f" ] || continue
        lebt "$(wert "$f" pid)" || continue
        echo "Zug wartet auf den Merge: $(wert "$f" reihenfolge) (Tree $(wert "$f" ziel | cut -c1-12), bis $(wert "$f" bis))"
    done
    n=0
    for f in "$ANFRAGEN"/*; do
        [ -e "$f" ] || continue
        lebt "$(wert "$f" pid)" || [ -n "$(wert "$f" ergebnis)" ] || continue
        n=$((n + 1))
        echo "Anfrage $n: PR #$(wert "$f" pr) ($(wert "$f" head | cut -c1-8)) $(wert "$f" ergebnis)"
    done
    command -v testplatz > /dev/null && testplatz --liste || "$HIER/testplatz.sh" --liste
    exit 0
fi

if [ "${1:-}" = "--fertig" ]; then
    letzte=$(ls -1t "$ZUG"/gruen-* 2> /dev/null | head -1 || true)
    [ -n "$letzte" ] || { echo "Zug: kein grüner Stand vermerkt." >&2; exit 2; }
    ziel=$(wert "$letzte" ziel)
    ende=$(($(date +%s) + WARTEN))
    while [ "$(date +%s)" -lt "$ende" ]; do
        m=$(main_holen) || exit 2
        if [ "$(tree "$m")" = "$ziel" ]; then
            echo "Zug: main $(git rev-parse --short "$m") hat den getesteten Stand ($(wert "$letzte" reihenfolge)). Ausrollbar."
            exit 0
        fi
        sleep 15
    done
    echo "Zug: der grüne Stand ist nach $WARTEN s nicht in main angekommen." >&2
    exit 1
fi

# --- Halten: Platz behalten, bis main den grünen Tree hat (eigener Prozess, von --innen gestartet) ---
if [ "${1:-}" = "--halten" ]; then
    gruen="$2"
    halten="$3"
    trap 'rm -f "$halten"' EXIT
    ziel=$(wert "$gruen" ziel)
    mapfile -t erlaubt < <(sed -n 's/^erlaubt=//p' "$gruen")
    ende=$(($(date +%s) + WARTEN))
    while [ "$(date +%s)" -lt "$ende" ]; do
        sleep 15
        m=$(main_holen 2> /dev/null) || continue
        t=$(tree "$m")
        if [ "$t" = "$ziel" ]; then echo "gemergt=$(date -Iseconds) $m" >> "$gruen"; exit 0; fi
        # Ein Zwischenstand des Bündels ist in Ordnung; ein fremder Merge beendet das Warten
        ok=0
        for e in "${erlaubt[@]}"; do [ "$t" = "$e" ] && ok=1; done
        if [ "$ok" = 0 ]; then echo "fremd=$(date -Iseconds) $m" >> "$gruen"; exit 0; fi
    done
    echo "abgelaufen=$(date -Iseconds)" >> "$gruen"
    exit 0
fi

# --- Innen: auf dem Zug-Platz ---
if [ "${1:-}" = "--innen" ]; then
    EIGEN="$2"
    erg=$(wert "$EIGEN" ergebnis)
    if [ -n "$erg" ]; then
        # Im Bündel eines anderen Laufs schon gefahren
        echo "Zug: PR #$(wert "$EIGEN" pr) fuhr schon im Bündel mit: $erg"
        rm -f "$EIGEN"
        case "$erg" in gruen*|gemergt*) exit 0 ;; *) exit 1 ;; esac
    fi
    while :; do
        # Offene Anfragen, älteste zuerst; die eigene ist dabei
        auswahl=()
        for f in "$ANFRAGEN"/*; do
            [ -e "$f" ] || continue
            [ -z "$(wert "$f" ergebnis)" ] || continue
            if ! lebt "$(wert "$f" pid)"; then rm -f "$f"; continue; fi
            auswahl+=("$f")
        done
        [ "${#auswahl[@]}" -gt 0 ] || { echo "Zug: nichts zu tun."; exit 0; }
        MAIN=$(main_holen) || exit 2
        echo "Zug: main ist $(git rev-parse --short "$MAIN")"
        WT=$(mktemp -d)
        git worktree add --quiet --detach "$WT" "$MAIN"
        aufraeumen() { git worktree remove --force "$WT" 2> /dev/null || rm -rf "$WT"; git worktree prune; }
        trap aufraeumen EXIT
        bund=()
        trees=()
        for f in "${auswahl[@]}"; do
            [ "${#bund[@]}" -lt "$BUENDEL" ] || break
            head=$(wert "$f" head)
            mig=0
            if git diff --name-only "$(git merge-base "$MAIN" "$head")" "$head" | grep -q '/migrations/'; then mig=1; fi
            # Ein PR mit Migrationen fährt allein
            if [ "$mig" = 1 ] && [ "${#bund[@]}" -gt 0 ]; then continue; fi
            if git -C "$WT" -c user.name="HUBIplan-Zug" -c user.email="zug@example.invalid" \
                merge --quiet --no-ff --no-edit -m "Zug: PR #$(wert "$f" pr)" "$head" > /dev/null 2>&1; then
                bund+=("$f")
                trees+=("$(git -C "$WT" rev-parse 'HEAD^{tree}')")
            else
                git -C "$WT" merge --abort 2> /dev/null || true
                echo "ergebnis=konflikt mit main $(git rev-parse --short "$MAIN")" >> "$f"
                echo "Zug: PR #$(wert "$f" pr) lässt sich nicht konfliktfrei auf main mischen, raus."
            fi
            [ "$mig" = 0 ] || break
        done
        if [ "${#bund[@]}" -eq 0 ]; then aufraeumen; trap - EXIT; continue; fi
        M=$(git -C "$WT" rev-parse HEAD)
        git update-ref "refs/zug/stand" "$M"
        prs=""
        for f in "${bund[@]}"; do prs+="${prs:+, }#$(wert "$f" pr)"; done
        echo "Zug: teste $prs auf main $(git rev-parse --short "$MAIN") als $(git rev-parse --short "$M")"
        aufraeumen
        trap - EXIT
        rc=0
        "$TEST" "$M" || rc=$?
        if [ "$rc" != 0 ]; then
            if [ "${#bund[@]}" -gt 1 ]; then
                # Bündel rot: der erste fährt allein noch einmal, die anderen kommen danach dran
                echo "Zug: Bündel $prs rot, der erste PR fährt allein weiter."
                for f in "${bund[@]:1}"; do echo "zurueck=$(date -Iseconds)" >> "$f"; done
                BUENDEL_ALT=$BUENDEL
                BUENDEL=1
                continue
            fi
            echo "ergebnis=rot (Lauf mit main $(git rev-parse --short "$MAIN"))" >> "${bund[0]}"
            echo "Zug: PR $prs ROT, raus. Beheben, dann neu einreihen."
            [ "${bund[0]}" = "$EIGEN" ] && { rm -f "$EIGEN"; exit 1; }
            BUENDEL=${BUENDEL_ALT:-$BUENDEL}
            continue
        fi
        # Grün: vermerken, dann den Platz halten, bis der Stand in main ist
        ziel=$(tree "$M")
        bis=$(date -d "@$(($(date +%s) + WARTEN))" -Iseconds)
        gruen="$ZUG/gruen-$(date +%s)-$$"
        { printf '%s\n' "ziel=$ziel" "main=$MAIN" "reihenfolge=$prs" "stand=$M" "erlaubt=$(tree "$MAIN")"
          for t in "${trees[@]}"; do echo "erlaubt=$t"; done; } > "$gruen"
        for f in "${bund[@]}"; do
            echo "ergebnis=gruen im Zug mit $prs (Tree $(echo "$ziel" | cut -c1-12)); gemergt wird von dem Thread, der den Zug gestartet hat" >> "$f"
        done
        echo
        echo "ZUG GRÜN: $prs auf main $(git rev-parse --short "$MAIN")."
        echo "Jetzt auf GitHub mergen, genau in dieser Reihenfolge, je mit „Create a merge commit“: $prs"
        echo "Der Zug hält seinen Platz bis $bis und gibt ihn frei, sobald main diesen Tree hat"
        echo "(prüfen mit: scripts/zug.sh --fertig). Danach ist main ohne neuen Lauf ausrollbar."
        halten="$ZUG/halten-$$"
        # Eigener Prozess (setsid): erbt die Sperre des Zug-Platzes und hält sie, auch wenn der
        # Aufrufer (Sitzung, Pipe) endet
        printf '%s\n' "ziel=$ziel" "reihenfolge=$prs" "bis=$bis" > "$halten"
        setsid "$0" --halten "$gruen" "$halten" < /dev/null > /dev/null 2>&1 &
        hpid=$!
        echo "pid=$hpid" >> "$halten"
        eigen=0
        for f in "${bund[@]}"; do [ "$f" = "$EIGEN" ] && eigen=1; done
        BUENDEL=${BUENDEL_ALT:-$BUENDEL}
        if [ "$eigen" = 1 ]; then rm -f "$EIGEN"; exit 0; fi
        # Der eigene PR war nicht dabei: warten, bis der Zug frei ist, dann weiter
        echo "Zug: der eigene PR #$(wert "$EIGEN" pr) fährt als Nächstes."
        while lebt "$hpid"; do sleep 5; done
    done
fi

# --- Einreihen ---
PR="${1:-}"
[[ "$PR" =~ ^[0-9]+$ ]] || { sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
holen "refs/pull/$PR/head" "refs/zug/pr-$PR" || { echo "Zug: PR #$PR ließ sich nicht holen." >&2; exit 2; }
HEAD_SHA=$(git rev-parse "refs/zug/pr-$PR")
echo "Zug: PR #$PR ($(git rev-parse --short "$HEAD_SHA"))"
if [ "${TEST_VORPRUEFUNG:-1}" = 1 ]; then "$HIER/vorpruefung.sh" "$HEAD_SHA" || exit $?; fi
ANFRAGE="$ANFRAGEN/$(date +%s%N)-$$"
printf '%s\n' "pid=$$" "pr=$PR" "head=$HEAD_SHA" "start=$(date -Iseconds)" > "$ANFRAGE"
export TEST_ANGEFRAGT="${TEST_ANGEFRAGT:-$(date +%s)}"
if [ -n "${TESTPLATZ:-}" ]; then exec "$0" --innen "$ANFRAGE"; fi
exec "$HIER/testplatz.sh" --zug "$0" --innen "$ANFRAGE"
