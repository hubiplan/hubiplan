#!/usr/bin/env bash
# Prüft deploy/aktualisierer/aktualisierer.sh (Selbstupdate) mit einem Wegwerf-Repository:
# Signatur, Rückschritt, Sperre, ungültige Aufträge, Ergebnis und Protokoll. Docker, systemd
# und das echte Ausrollen ersetzt ein Platzhalter (HUBIPLAN_SETUP). Aufruf aus scripts/test.sh:
#   scripts/pruefe-aktualisierer.sh <Ordner mit deploy/aktualisierer>
set -euo pipefail

QUELLE_SKRIPT="$(cd "${1:-$(dirname "$0")/..}" && pwd)/deploy/aktualisierer/aktualisierer.sh"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
FEHLER=0
pruefe() {
    if [ "$2" = "$3" ]; then echo "  ok: $1"; else echo "  FEHLER: $1 (erwartet „$3“, war „$2“)"; FEHLER=1; fi
}

ssh-keygen -q -t ed25519 -N "" -C release -f "$T/schluessel"
ssh-keygen -q -t ed25519 -N "" -C fremd -f "$T/fremd"
# Eigene Git-Einstellungen des Rechners (Signierprogramm, gpgsign) gelten hier nicht
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
G=(git -c user.email=t@example.org -c user.name=Test -c gpg.format=ssh -c init.defaultBranch=main)

# Repository mit drei Releases: v2026.11.0, v2026.12.0 (signiert), v2026.12.1 (fremder Schlüssel)
"${G[@]}" init -q "$T/repo"
mkdir -p "$T/repo/deploy"
echo "releases@hubiplan namespaces=\"git\" $(cat "$T/schluessel.pub")" > "$T/repo/deploy/release-schluessel"
echo 1 > "$T/repo/inhalt"
"${G[@]}" -C "$T/repo" add -A
"${G[@]}" -C "$T/repo" commit -q -m eins
"${G[@]}" -C "$T/repo" -c user.signingkey="$T/schluessel.pub" tag -s -m eins v2026.11.0
echo 2 > "$T/repo/inhalt"
"${G[@]}" -C "$T/repo" commit -q -am zwei
"${G[@]}" -C "$T/repo" -c user.signingkey="$T/schluessel.pub" tag -s -m zwei v2026.12.0
"${G[@]}" -C "$T/repo" tag -a -m unsigniert v2026.12.2
echo 3 > "$T/repo/inhalt"
"${G[@]}" -C "$T/repo" commit -q -am drei
"${G[@]}" -C "$T/repo" -c user.signingkey="$T/fremd.pub" tag -s -m drei v2026.12.1

# Server: läuft v2026.11.0
ZIEL="$T/opt/hubiplan"
mkdir -p "$ZIEL/deploy" "$T/auftrag"
cp "$T/repo/deploy/release-schluessel" "$ZIEL/deploy/"
git -C "$T/repo" rev-parse v2026.11.0^{commit} > "$ZIEL/.fassung"
cat > "$ZIEL/.env" << ENV
HUBIPLAN_SELBSTUPDATE=1
AKTUALISIERUNG_DIR=$T/auftrag
HUBIPLAN_UPDATE_REPO=$T/repo
ENV
export HUBIPLAN_SETUP="cat inhalt > '$T/setup.lauf'" HUBIPLAN_OHNE_SICHERUNG=1 \
    HUBIPLAN_MIN_FREI_MB=0 HUBIPLAN_DOCKER_DIR=/
lauf() {
    rm -f "$T/auftrag/ergebnis" "$T/setup.lauf"
    [ -z "$1" ] || echo "version=$1" > "$T/auftrag/auftrag"
    bash "$QUELLE_SKRIPT" "$ZIEL" > /dev/null 2>&1 || true
}
status() { sed -n 's/^status=//p' "$T/auftrag/ergebnis" 2> /dev/null || echo keins; }

echo "Aktualisierer:"
lauf ""
pruefe "ohne Auftrag nichts" "$(status)" keins
lauf "2026.12.1"
pruefe "fremder Schlüssel abgelehnt" "$(status)" fehler
pruefe "  dabei nichts ausgerollt" "$([ -f "$T/setup.lauf" ] && echo ja || echo nein)" nein
lauf "2026.12.2"
pruefe "unsignierter Tag abgelehnt" "$(status)" fehler
lauf "2026.13.0"
pruefe "unbekannte Version abgelehnt" "$(status)" fehler
lauf "../x"
pruefe "ungültiger Auftrag abgelehnt" "$(status)" fehler
mkdir "$ZIEL.sperre"
lauf "2026.12.0"
pruefe "Sperre beachtet" "$(status)" fehler
rmdir "$ZIEL.sperre"
lauf "2026.12.0"
pruefe "signiertes Release ausgerollt" "$(status)" ok
pruefe "  Inhalt der neuen Fassung" "$(cat "$T/setup.lauf" 2> /dev/null)" 2
pruefe "  Auftrag erledigt" "$([ -e "$T/auftrag/auftrag" ] || [ -e "$T/auftrag/auftrag.laeuft" ] && echo offen || echo erledigt)" erledigt
pruefe "  Protokoll" "$(awk '{print $3, $4, $5}' "$ZIEL.protokoll" | tail -n1)" "2026.12.0 selbstupdate ausgerollt"
pruefe "  Sperre wieder frei" "$([ -d "$ZIEL.sperre" ] && echo belegt || echo frei)" frei
# Der Platzhalter tauscht nicht: Server meldet jetzt v2026.12.0 als laufend
git -C "$T/repo" rev-parse v2026.12.0^{commit} > "$ZIEL/.fassung"
lauf "2026.11.0"
pruefe "Rückschritt abgelehnt" "$(status)" fehler
sed -i 's/^HUBIPLAN_SELBSTUPDATE=1/HUBIPLAN_SELBSTUPDATE=0/' "$ZIEL/.env"
echo "version=2026.12.0" > "$T/auftrag/auftrag"
bash "$QUELLE_SKRIPT" "$ZIEL" > /dev/null 2>&1 || true
pruefe "ausgeschaltet: Auftrag bleibt liegen" "$([ -f "$T/auftrag/auftrag" ] && echo liegt || echo weg)" liegt

[ "$FEHLER" = 0 ] || { echo "Aktualisierer: Fehler" >&2; exit 1; }
echo "Aktualisierer: ok"
