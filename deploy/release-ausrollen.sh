#!/usr/bin/env bash
# Rollt ein Release (Tag) auf einen Server aus: erst HUBIplan, danach auf Wunsch die Webseite
# (konzepte/releases.md, R5; docs/releases.md). Läuft in WSL im Klon ~/hubiplan:
#
#   deploy/release-ausrollen.sh produktion v2026.11.1
#   deploy/release-ausrollen.sh produktion v2026.11.1 --webseite v2026.11.1
#   deploy/release-ausrollen.sh testserver v2026.11.1
#
# Das Ziel steht nur lokal in ~/.config/hubiplan/ziele/<name>, je Zeile NAME=WERT
# (erlaubt: DEPLOY_HOST, SSH, DEPLOY_SUDO, DEPLOY_KEY). „testserver“ geht auch ohne Datei
# (wie deploy/deploy.sh: Ziel aus ~/.config/hubiplan/testserver). Beispiel für produktion:
#   SSH=/mnt/c/Windows/System32/OpenSSH/ssh.exe
#   DEPLOY_HOST=deploy@server.example.org
#   DEPLOY_SUDO=1
#
# Prüft vorher je Programm: Tag vorhanden und Release-Form, der laufende Stand ist im Tag
# enthalten (kein Rückschritt), lokal getestet (prüft deploy.sh). Steht in den Änderungen seit
# dem laufenden Stand „Kein Rückweg“, sichert es vorher die Datenbank und fragt nach.
# Ausgerollt wird aus einem eigenen Worktree (RELEASE_TMP, Standard /mnt/e/temp/hubiplan-release),
# damit ~/hubiplan nicht umgeschaltet wird.
set -euo pipefail

abbruch() {
    echo "Abbruch: $*" >&2
    exit 1
}

[ $# -ge 2 ] || abbruch "Aufruf: deploy/release-ausrollen.sh <ziel> <tag> [--webseite <tag>]"
ZIEL="$1"
TAG="$2"
shift 2
WEB_TAG=""
while [ $# -gt 0 ]; do
    case "$1" in
        --webseite)
            [ $# -ge 2 ] || abbruch "--webseite braucht einen Tag."
            WEB_TAG="$2"
            shift 2
            ;;
        *) abbruch "unbekannte Angabe „$1“." ;;
    esac
done
case "$ZIEL" in
    *[!A-Za-z0-9_-]* | "") abbruch "Zielname „$ZIEL“ ungültig." ;;
esac
release_tag() {
    [[ "$1" =~ ^v[0-9]{4}\.[0-9]{1,2}\.[0-9]+$ ]] || abbruch "„$1“ ist kein Release-Tag (vJJJJ.MM.N)."
}
release_tag "$TAG"
[ -z "$WEB_TAG" ] || release_tag "$WEB_TAG"

REPO="$(git rev-parse --show-toplevel)"
WEB_REPO="${WEBSITE_REPO:-$HOME/hubiplan-website}"
TMP="${RELEASE_TMP:-/mnt/e/temp/hubiplan-release}"

# Ziel laden: nur bekannte Namen, Werte ohne Anführungszeichen
ZIEL_DATEI="${HUBIPLAN_ZIELE:-$HOME/.config/hubiplan/ziele}/$ZIEL"
if [ -f "$ZIEL_DATEI" ]; then
    while IFS= read -r zeile || [ -n "$zeile" ]; do
        case "$zeile" in "" | \#*) continue ;; esac
        name="${zeile%%=*}"
        wert="${zeile#*=}"
        wert="${wert/#\~/$HOME}"
        case "$name" in
            DEPLOY_HOST | SSH | DEPLOY_SUDO | DEPLOY_KEY) export "$name=$wert" ;;
            *) abbruch "$ZIEL_DATEI: unbekannte Angabe „$name“." ;;
        esac
    done < "$ZIEL_DATEI"
elif [ "$ZIEL" != testserver ]; then
    abbruch "Ziel „$ZIEL“ unbekannt: $ZIEL_DATEI fehlt (siehe Kopf dieses Skripts)."
fi
if [ -z "${DEPLOY_HOST:-}" ]; then
    DEPLOY_HOST="$(head -n1 "$HOME/.config/hubiplan/testserver" 2> /dev/null || true)"
    [ -n "$DEPLOY_HOST" ] || abbruch "Kein DEPLOY_HOST für „$ZIEL“."
fi
SSH="${SSH:-ssh}"
SSH_ARGS=()
[ -z "${DEPLOY_KEY:-}" ] || SSH_ARGS=(-i "$DEPLOY_KEY" -o IdentitiesOnly=yes)
SUDO=""
[ -z "${DEPLOY_SUDO:-}" ] || SUDO="sudo "
auf_server() {
    "$SSH" "${SSH_ARGS[@]}" "$DEPLOY_HOST" "$@"
}

# Prüfen, ob ein Programm ausgerollt werden darf. Gibt „gleich“ oder „neu“ aus.
pruefen() {
    local repo="$1" tag="$2" dir="$3" name="$4" commit laufend
    git -C "$repo" fetch -q --tags origin 2> /dev/null ||
        echo "$name: Tags nicht geholt (origin nicht erreichbar), nehme die vorhandenen." >&2
    commit=$(git -C "$repo" rev-parse -q --verify "refs/tags/$tag^{commit}") ||
        abbruch "$name: Tag $tag fehlt. Im Windows-Klon erst „git fetch --tags“ ausführen."
    laufend=$(auf_server "cat '$dir/.fassung' 2> /dev/null" || true)
    laufend="${laufend//[[:space:]]/}"
    if [ -z "$laufend" ]; then
        echo "$name: auf $ZIEL läuft noch keine bekannte Fassung." >&2
    else
        [[ "$laufend" =~ ^[0-9a-f]{40}$ ]] || abbruch "$name: $dir/.fassung unlesbar."
        git -C "$repo" cat-file -e "$laufend^{commit}" 2> /dev/null ||
            abbruch "$name: laufender Stand ${laufend:0:7} ist hier unbekannt. Erst holen (git fetch)."
        if [ "$laufend" = "$commit" ]; then
            echo "gleich"
            return
        fi
        git -C "$repo" merge-base --is-ancestor "$laufend" "$commit" ||
            abbruch "$name: $tag enthält den laufenden Stand ${laufend:0:7} nicht (Rückschritt). Zurück nur mit deploy/zurueck.sh."
        if git -C "$repo" diff "$laufend" "$commit" -- CHANGELOG.md | grep -q '^+.*Kein Rückweg'; then
            echo "kein-rueckweg"
            return
        fi
    fi
    echo "neu"
}

# Zusätzliche Datenbanksicherung vor einem Release ohne Rückweg (konzepte/releases.md, 5.2)
sichern() {
    local dir="$1"
    echo "Sichere vorher die Datenbank auf $ZIEL (Backup-Dienst, wie das tägliche Backup) …"
    if ! auf_server "cd '$dir' && ${SUDO}sh -s" << 'SKRIPT'
set -eu
PROJEKT=$(grep '^COMPOSE_PROJECT_NAME=' .env | cut -d= -f2 || true)
PROJEKT=${PROJEKT:-$(basename "$(pwd)")}
DATEIEN="-f docker-compose.server.yml"
grep -q '^HUBIPLAN_HINTER_PROXY=1' .env && DATEIEN="$DATEIEN -f docker-compose.proxy.yml"
grep -q '^CLAMD_SOCKET_DIR=.' .env && DATEIEN="$DATEIEN -f docker-compose.clamav.yml"
docker compose -p "$PROJEKT" $DATEIEN exec -T backup backup.sh
SKRIPT
    then
        abbruch "Sicherung auf $ZIEL fehlgeschlagen; nichts ausgerollt."
    fi
    echo "Sicherung fertig (liegt bei den täglichen Backups)."
}

nachfragen() {
    local frage="$1" antwort
    if [ ! -t 0 ]; then
        [ "${RELEASE_OHNE_RUECKWEG:-}" = ja ] || abbruch "$frage Ohne Terminal nur mit RELEASE_OHNE_RUECKWEG=ja."
        return
    fi
    read -r -p "$frage Weiter? (ja/nein) " antwort
    [ "$antwort" = ja ] || abbruch "nicht bestätigt."
}

# Aus einem Worktree des Tags mit dessen eigenem deploy.sh ausrollen
ausrollen() {
    local repo="$1" tag="$2" dir="$3" name="$4" wt commit
    commit=$(git -C "$repo" rev-parse "refs/tags/$tag^{commit}")
    mkdir -p "$TMP"
    wt="$TMP/$name-$tag"
    git -C "$repo" worktree remove --force "$wt" 2> /dev/null || true
    git -C "$repo" worktree add -q --detach "$wt" "$commit"
    local rc=0
    (cd "$wt" && DEPLOY_DIR="$dir" deploy/deploy.sh "$commit") || rc=$?
    git -C "$repo" worktree remove --force "$wt" || true
    [ "$rc" -eq 0 ] || abbruch "$name: Ausrollen von $tag fehlgeschlagen ($rc)."
    local version
    version=$(auf_server "cat '$dir/.version' 2> /dev/null" || true)
    version="${version//[[:space:]]/}"
    [ "$version" = "${tag#v}" ] || abbruch "$name: auf $ZIEL läuft „$version“ statt ${tag#v}."
    echo "$name: $tag läuft auf $ZIEL."
}

PROGRAMME=("$REPO|$TAG|/opt/hubiplan|hubiplan")
if [ -n "$WEB_TAG" ]; then
    [ -d "$WEB_REPO/.git" ] || abbruch "Webseiten-Klon $WEB_REPO fehlt (WEBSITE_REPO setzen)."
    PROGRAMME+=("$WEB_REPO|$WEB_TAG|/opt/hubiplan-website|webseite")
fi

# Erst alles prüfen, dann ausrollen: So bricht ein Fehler bei der Webseite nicht erst ab,
# wenn HUBIplan schon neu läuft.
ZUSTAND=()
for p in "${PROGRAMME[@]}"; do
    IFS='|' read -r repo tag dir name <<< "$p"
    ZUSTAND+=("$(pruefen "$repo" "$tag" "$dir" "$name")")
done

i=0
for p in "${PROGRAMME[@]}"; do
    IFS='|' read -r repo tag dir name <<< "$p"
    case "${ZUSTAND[$i]}" in
        gleich) echo "$name: $tag läuft auf $ZIEL schon." ;;
        kein-rueckweg)
            echo "$name: Seit dem laufenden Stand gibt es eine Änderung ohne Rückweg über zurueck.sh."
            nachfragen "$name $tag hat keinen Rückweg; HUBIplan sichert vorher die Datenbank."
            if [ "$name" = hubiplan ]; then sichern "$dir"; fi
            ausrollen "$repo" "$tag" "$dir" "$name"
            ;;
        *) ausrollen "$repo" "$tag" "$dir" "$name" ;;
    esac
    i=$((i + 1))
done
