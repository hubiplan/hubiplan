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
#
# Der Auftragsordner gehört dem Backend (UID 1000). Darin öffnet dieses Skript (root) keine
# Datei zum Schreiben: Ergebnis und Ausgaben entstehen in einem eigenen Ordner nur für root
# (AKTUALISIERUNG_DIR.root) und landen per Umbenennen im Auftragsordner. Ein Symlink dort
# kann so keine fremde Datei überschreiben (Audit 03.11. GA-S10).
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

DIR="${DIR%/}"
[ -f "$DIR/auftrag" ] || exit 0

# Eigener Ordner nur für root, neben dem Auftragsordner (gleiches Dateisystem zum Umbenennen)
PRIVAT="$DIR.root"
if [ -L "$PRIVAT" ] || { [ -e "$PRIVAT" ] && [ ! -d "$PRIVAT" ]; }; then
    echo "Abbruch: $PRIVAT ist kein Ordner." >&2
    exit 1
fi
mkdir -p "$PRIVAT"
chmod 700 "$PRIVAT"
if [ "$(stat -c %u "$PRIVAT")" != "$(id -u)" ] ||
    [ "$(stat -c %d "$PRIVAT")" != "$(stat -c %d "$DIR")" ]; then
    echo "Abbruch: $PRIVAT gehört nicht $(id -un) oder liegt auf einem anderen Dateisystem als $DIR." >&2
    exit 1
fi

# Auftrag übernehmen; ein zweiter Lauf findet ihn dann nicht mehr
mv -T "$DIR/auftrag" "$DIR/auftrag.laeuft" 2> /dev/null || exit 0

# Datei aus PRIVAT in den Auftragsordner legen: rename ersetzt einen Symlink, folgt ihm nicht
ablegen() {
    chmod 644 "$1"
    mv -fT "$1" "$DIR/$2"
}

ergebnis() {
    local status="$1" text="$2" neu
    neu="$(mktemp "$PRIVAT/ergebnis.XXXXXX")"
    {
        echo "status=$status"
        echo "version=${VERSION:-}"
        echo "zeit=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo "text=${text//$'\n'/ }"
    } > "$neu"
    ablegen "$neu" ergebnis
    # „laeuft“ ist ein Zwischenstand; der Auftrag bleibt dabei übernommen
    [ "$status" = laeuft ] || rm -f "$DIR/auftrag.laeuft"
    echo "$status: $text"
}
fehler() {
    ergebnis fehler "$1"
    exit 1
}
status_schreiben() {
    ergebnis laeuft "$1"
}

# Nur eine kleine, gewöhnliche Datei lesen (kein Symlink, keine Pipe)
[ -f "$DIR/auftrag.laeuft" ] && [ ! -L "$DIR/auftrag.laeuft" ] || fehler "Ungültiger Auftrag."
VERSION="$(head -c 200 "$DIR/auftrag.laeuft" | sed -n 's/^version=//p' | head -n1)"
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
    # Nur für scripts/pruefe-aktualisierer.sh: Docker durch einen Platzhalter ersetzen
    if [ -n "${HUBIPLAN_COMPOSE:-}" ]; then
        "$HUBIPLAN_COMPOSE" "$@"
        return
    fi
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
    compose exec -T backup backup.sh > "$PRIVAT/sicherung.log" 2>&1 ||
        fehler "Sicherung fehlgeschlagen; nichts geändert (sicherung.log in $PRIVAT)."
    # Fehlen Dateien oder die Schlüsselkopie, endet backup.sh trotzdem mit 0 und hinterlässt
    # .unvollstaendig. Dann nicht ausrollen (Audit 03.11. GA-F11).
    # shellcheck disable=SC2016 # $BACKUP_DIR gilt im Container
    if ! compose exec -T backup sh -c 'test ! -e "${BACKUP_DIR:-/backups}/.unvollstaendig"' \
        >> "$PRIVAT/sicherung.log" 2>&1; then
        fehler "Sicherung unvollständig; nichts geändert (Backup-Status in HUBIplan, sicherung.log in $PRIVAT)."
    fi
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
if (cd "$NEU" && ZIEL="$ZIEL" bash -c "$SETUP") > "$PRIVAT/ausrollen.log" 2>&1; then
    protokoll ausgerollt
    ergebnis ok "$TAG läuft."
else
    rc=$?
    protokoll "fehlgeschlagen ($rc)"
    fehler "Ausrollen von $TAG fehlgeschlagen ($rc); die vorige Fassung läuft weiter (ausrollen.log in $PRIVAT)."
fi
