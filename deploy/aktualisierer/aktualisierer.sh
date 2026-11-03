#!/usr/bin/env bash
# Selbstupdate (konzepte/selbstupdate.md, 7b): arbeitet einen Auftrag aus HUBIplan ab.
# Läuft auf dem Server als root, außerhalb der Container, gestartet von einem systemd-Timer
# (eingerichtet von deploy/server-setup.sh, wenn in der .env HUBIPLAN_SELBSTUPDATE=1 steht):
#
#   aktualisierer.sh /opt/hubiplan
#
# HUBIplan schreibt nur die Datei „auftrag“ (version=2026.12.0) in den Auftragsordner
# (AKTUALISIERUNG_DIR, Standard /opt/hubiplan-aktualisierung). Alles Weitere entscheidet dieses
# Skript: Es nimmt nur einen Release-Tag aus dem eingetragenen Repository, dessen Signatur zu
# deploy/release-schluessel der LAUFENDEN Fassung passt und der den laufenden Stand enthält.
# Vorher sichert es die Datenbank, dann rollt es aus wie deploy.sh (server-setup.sh mit
# automatischem Rückweg). Das Ergebnis steht in „ergebnis“, das Protokoll in ZIEL.protokoll.
set -euo pipefail

ZIEL="${1:-/opt/hubiplan}"
ZIEL="${ZIEL%/}"
[ -f "$ZIEL/.env" ] || exit 0
wert() {
    grep "^$1=" "$ZIEL/.env" | tail -n1 | cut -d= -f2- || true
}
[ "$(wert HUBIPLAN_SELBSTUPDATE)" = 1 ] || exit 0

DIR="$(wert AKTUALISIERUNG_DIR)"
DIR="${DIR:-/opt/hubiplan-aktualisierung}"
REPO_URL="$(wert HUBIPLAN_UPDATE_REPO)"
REPO_URL="${REPO_URL:-https://github.com/hubiplan/hubiplan.git}"
QUELLE="${HUBIPLAN_QUELLE:-$ZIEL-quelle.git}"
SETUP="${HUBIPLAN_SETUP:-sh deploy/server-setup.sh}"
MIN_FREI_MB="${HUBIPLAN_MIN_FREI_MB:-4096}"
DOCKER_DIR="${HUBIPLAN_DOCKER_DIR:-/var/lib/docker}"

[ -f "$DIR/auftrag" ] || exit 0
# Auftrag übernehmen; ein zweiter Lauf findet ihn dann nicht mehr
mv "$DIR/auftrag" "$DIR/auftrag.laeuft" 2> /dev/null || exit 0

ergebnis() {
    local status="$1" text="$2"
    {
        echo "status=$status"
        echo "version=${VERSION:-}"
        echo "zeit=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo "text=${text//$'\n'/ }"
    } > "$DIR/ergebnis.neu"
    chmod 644 "$DIR/ergebnis.neu"
    mv "$DIR/ergebnis.neu" "$DIR/ergebnis"
    rm -f "$DIR/auftrag.laeuft"
    echo "$status: $text"
}
fehler() {
    ergebnis fehler "$1"
    exit 1
}
status_schreiben() {
    ergebnis laeuft "$1"
    # „laeuft“ ist ein Zwischenstand; der Auftrag bleibt dabei übernommen
    : > "$DIR/auftrag.laeuft"
}

VERSION="$(sed -n 's/^version=//p' "$DIR/auftrag.laeuft" | head -n1)"
[[ "$VERSION" =~ ^[0-9]{4}\.[0-9]{1,2}\.[0-9]+$ ]] || fehler "Ungültiger Auftrag."
TAG="v$VERSION"

# Sperre wie deploy.sh: nie zwei Läufe gleichzeitig
SPERRE="$ZIEL.sperre"
if ! mkdir "$SPERRE" 2> /dev/null; then
    fehler "Gerade läuft schon ein Ausrollen. Bitte später noch einmal."
fi
echo "$TAG $(date -u +%Y-%m-%dT%H:%M:%SZ) selbstupdate" > "$SPERRE/lauf"
trap 'rm -rf "$SPERRE"' EXIT

status_schreiben "Hole $TAG …"
if [ ! -d "$QUELLE" ]; then
    git clone --quiet --bare "$REPO_URL" "$QUELLE" || fehler "Repository nicht erreichbar."
fi
git -C "$QUELLE" fetch --quiet --force --tags "$REPO_URL" '+refs/heads/main:refs/heads/main' ||
    fehler "Repository nicht erreichbar."
COMMIT="$(git -C "$QUELLE" rev-parse -q --verify "refs/tags/$TAG^{commit}")" ||
    fehler "Release $TAG gibt es im Repository nicht."

# Echtheit: signiert mit einem Schlüssel aus der laufenden Fassung
SCHLUESSEL="$ZIEL/deploy/release-schluessel"
grep -q '^[^#[:space:]]' "$SCHLUESSEL" 2> /dev/null || fehler "Kein Release-Schlüssel in der laufenden Fassung."
git -C "$QUELLE" -c gpg.ssh.program=ssh-keygen -c gpg.ssh.allowedSignersFile="$SCHLUESSEL" tag -v "$TAG" > /dev/null 2>&1 ||
    fehler "Signatur von $TAG ist ungültig. Nichts geändert."

# Kein Rückschritt: der laufende Stand steckt im neuen
LAUFEND="$(tr -d '[:space:]' < "$ZIEL/.fassung" 2> /dev/null || true)"
[[ "$LAUFEND" =~ ^[0-9a-f]{40}$ ]] || fehler "Laufender Stand unbekannt (.fassung fehlt)."
[ "$LAUFEND" != "$COMMIT" ] || { ergebnis ok "$TAG läuft schon."; exit 0; }
git -C "$QUELLE" merge-base --is-ancestor "$LAUFEND" "$COMMIT" 2> /dev/null ||
    fehler "$TAG enthält den laufenden Stand nicht (Rückschritt)."

# Platz zum Bauen
FREI_MB=$(df -Pm "$DOCKER_DIR" 2> /dev/null | awk 'NR==2 {print $4}')
if [ -n "$FREI_MB" ] && [ "$FREI_MB" -lt "$MIN_FREI_MB" ]; then
    fehler "Zu wenig Platz zum Bauen ($FREI_MB MB frei, nötig $MIN_FREI_MB MB)."
fi

compose() {
    local projekt dateien
    projekt="$(wert COMPOSE_PROJECT_NAME)"
    projekt="${projekt:-$(basename "$ZIEL")}"
    dateien=(-f docker-compose.server.yml)
    [ "$(wert HUBIPLAN_HINTER_PROXY)" = 1 ] && dateien+=(-f docker-compose.proxy.yml)
    [ -n "$(wert CLAMD_SOCKET_DIR)" ] && dateien+=(-f docker-compose.clamav.yml)
    [ -f "$ZIEL/docker-compose.selbstupdate.yml" ] && dateien+=(-f docker-compose.selbstupdate.yml)
    (cd "$ZIEL" && docker compose -p "$projekt" "${dateien[@]}" "$@")
}

if [ -z "${HUBIPLAN_OHNE_SICHERUNG:-}" ]; then
    status_schreiben "Sichere die Datenbank …"
    compose exec -T backup backup.sh > "$DIR/sicherung.log" 2>&1 ||
        fehler "Sicherung fehlgeschlagen; nichts geändert (sicherung.log)."
fi

protokoll() {
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ${COMMIT:0:7} $VERSION selbstupdate $1" >> "$ZIEL.protokoll"
}

status_schreiben "Baue und starte $TAG …"
NEU="$ZIEL.neu"
rm -rf "$NEU"
mkdir -p "$NEU"
chmod 755 "$NEU"
cp -p "$ZIEL/.env" "$NEU/.env"
git -C "$QUELLE" archive --format=tar "$COMMIT" | tar -x --no-same-owner -C "$NEU"
echo "$COMMIT" > "$NEU/.fassung"
echo "$VERSION" > "$NEU/.version"
if (cd "$NEU" && ZIEL="$ZIEL" bash -c "$SETUP") > "$DIR/ausrollen.log" 2>&1; then
    protokoll ausgerollt
    ergebnis ok "$TAG läuft."
else
    rc=$?
    protokoll "fehlgeschlagen ($rc)"
    fehler "Ausrollen von $TAG fehlgeschlagen ($rc); die vorige Fassung läuft weiter (ausrollen.log)."
fi
