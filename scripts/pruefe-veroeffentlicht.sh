#!/usr/bin/env bash
# Prüft deploy/veroeffentlicht.sh und dessen Einbindung in deploy/deploy.sh (AGPL § 13,
# Gesamtaudit 15.11., OPS-13) mit Wegwerf-Repositorys: ein nacktes „öffentliches“
# Repository und ein Klon mit einem nicht gepushten Commit. Kein Netz, kein Server, kein Docker.
#   scripts/pruefe-veroeffentlicht.sh <repo-wurzel>
set -euo pipefail
ROOT="$(cd "${1:-.}" && pwd)"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
export GIT_AUTHOR_NAME=Test GIT_AUTHOR_EMAIL=test@example.org
export GIT_COMMITTER_NAME=Test GIT_COMMITTER_EMAIL=test@example.org
export GIT_CONFIG_NOSYSTEM=1 HOME="$T/home"
mkdir -p "$HOME"
unset HUBIPLAN_UNVEROEFFENTLICHT_ERLAUBT GIT_ALLOW_PROTOCOL || true

fehler() {
    echo "Veröffentlichungsprüfung: $*" >&2
    exit 1
}

# Öffentliches Repository mit main, einem älteren Release-Tag und einem neueren Stand
PUB="$T/oeffentlich.git"
git init -q --bare "$PUB"
LOKAL="$T/lokal"
git init -q "$LOKAL"
cd "$LOKAL"
mkdir deploy
cp "$ROOT/deploy/veroeffentlicht.sh" "$ROOT/deploy/deploy.sh" deploy/
printf 'services: {}\n' > docker-compose.server.yml
git add -A
git commit -q -m alt
ALT=$(git rev-parse HEAD)
git tag -a v2026.11.0 -m Release
echo neu > neu.txt
git add neu.txt
git commit -q -m neu
VEROEFFENTLICHT=$(git rev-parse HEAD)
git push -q "$PUB" HEAD:refs/heads/main refs/tags/v2026.11.0
# Nur über einen Tag erreichbar (Release-Zweig gelöscht)
git checkout -q -b nur-tag "$ALT"
echo tag > tag.txt
git add tag.txt
git commit -q -m nur-tag
NUR_TAG=$(git rev-parse HEAD)
git tag -a v2026.11.1 -m Release
git push -q "$PUB" refs/tags/v2026.11.1
git checkout -q "$VEROEFFENTLICHT"
# Lokaler, nicht gepushter Commit
echo geheim > lokal.txt
git add lokal.txt
git commit -q -m lokal
LOKAL_COMMIT=$(git rev-parse HEAD)
cd "$T"

# shellcheck source=deploy/veroeffentlicht.sh
. "$ROOT/deploy/veroeffentlicht.sh"
REFS_VORHER=$(git -C "$LOKAL" for-each-ref | sort)

pruefe() {
    local erwartet="$1" muster="$2" rc=0
    shift 2
    veroeffentlicht_pruefen "$@" > "$T/aus" 2>&1 || rc=$?
    [ "$rc" = "$erwartet" ] || { cat "$T/aus" >&2; fehler "$* ergab $rc statt $erwartet"; }
    grep -q -- "$muster" "$T/aus" || { cat "$T/aus" >&2; fehler "$* ohne „$muster“"; }
}

# Veröffentlicht: aktueller Stand, älterer Stand (Rückweg/zurück zu einer Vorfassung), nur per Tag
pruefe 0 "Veröffentlicht: ${VEROEFFENTLICHT:0:7}" "$LOKAL" "$VEROEFFENTLICHT" "$PUB"
pruefe 0 "Veröffentlicht: ${ALT:0:7}" "$LOKAL" "$ALT" "file://$PUB"
pruefe 0 "Veröffentlicht: ${NUR_TAG:0:7}" "$LOKAL" "$NUR_TAG" "$PUB"
pruefe 0 "Veröffentlicht" "$LOKAL" v2026.11.1 "$PUB"
# Nicht gepusht: Abbruch mit Hinweis auf Push und Testserver-Schalter
pruefe 1 "nicht enthalten" "$LOKAL" "$LOKAL_COMMIT" "$PUB"
pruefe 1 "HUBIPLAN_UNVEROEFFENTLICHT_ERLAUBT=1" "$LOKAL" "$LOKAL_COMMIT" "$PUB"
# Nicht erreichbar oder unbrauchbar: nie „veröffentlicht“ (fail closed)
pruefe 2 "nicht erreichbar" "$LOKAL" "$VEROEFFENTLICHT" "$T/gibt-es-nicht.git"
pruefe 2 "nicht erreichbar" "$LOKAL" "$VEROEFFENTLICHT" "file://$T/gibt-es-nicht.git"
pruefe 2 "nicht erreichbar" "$LOKAL" "$VEROEFFENTLICHT" "ext::sh -c touch% $T/ext-ausgefuehrt"
[ ! -e "$T/ext-ausgefuehrt" ] || fehler "ext::-Transport ausgeführt"
pruefe 2 "Keine gültige Adresse" "$LOKAL" "$VEROEFFENTLICHT" ""
pruefe 2 "Keine gültige Adresse" "$LOKAL" "$VEROEFFENTLICHT" "--upload-pack=touch"
pruefe 2 "unbekannt" "$LOKAL" "0000000000000000000000000000000000000000" "$PUB"
# Testserver-Schalter: übersprungen, mit sichtbarer Warnung, auch ohne erreichbares Repository
HUBIPLAN_UNVEROEFFENTLICHT_ERLAUBT=1 pruefe 0 "WARNUNG" "$LOKAL" "$LOKAL_COMMIT" "$T/gibt-es-nicht.git"
HUBIPLAN_UNVEROEFFENTLICHT_ERLAUBT=1 pruefe 0 "Nur für reine Testserver" "$LOKAL" "$LOKAL_COMMIT" "$PUB"
# Andere Werte schalten nichts frei
HUBIPLAN_UNVEROEFFENTLICHT_ERLAUBT=ja pruefe 1 "nicht enthalten" "$LOKAL" "$LOKAL_COMMIT" "$PUB"
# Das lokale Repository bekommt keine Referenzen aus dem öffentlichen
[ "$(git -C "$LOKAL" for-each-ref | sort)" = "$REFS_VORHER" ] || fehler "lokale Referenzen verändert"
# Einzelaufruf als Skript
bash "$ROOT/deploy/veroeffentlicht.sh" "$LOKAL" "$VEROEFFENTLICHT" "$PUB" > /dev/null
if bash "$ROOT/deploy/veroeffentlicht.sh" "$LOKAL" "$LOKAL_COMMIT" "$PUB" 2> /dev/null; then
    fehler "Skriptaufruf ließ unveröffentlichten Commit durch"
fi

# Einbindung in deploy.sh: SSH-Ersatz liefert die .env-Adresse und protokolliert jeden Aufruf.
# Die Serversperre (mkdir) lässt er scheitern; bis dahin darf deploy.sh nur gelesen haben.
cat > "$T/ssh" << 'SSH'
#!/usr/bin/env bash
shift
printf '%s\n' "$*" >> "$SSH_LOG"
case "$*" in
    # Wie sed auf dem Server: nur der Wert, hier mit Anführungszeichen und CRLF
    *HUBIPLAN_SOURCE_URL*) [ -z "$ENV_URL" ] || printf '"%s"\r\n' "$ENV_URL" ;;
    *mkdir*) exit 1 ;;
    *) exit 0 ;;
esac
SSH
chmod +x "$T/ssh"
export SSH="$T/ssh" SSH_LOG="$T/ssh.log" DEPLOY_HOST=test@server.example.org
export HUBIPLAN_TESTED_FILE="$T/getestet"
for c in "$VEROEFFENTLICHT" "$LOKAL_COMMIT"; do
    echo "$(git -C "$LOKAL" rev-parse "$c^{tree}") $c" >> "$HUBIPLAN_TESTED_FILE"
done
deploy() {
    local rc=0
    : > "$SSH_LOG"
    (cd "$LOKAL" && bash deploy/deploy.sh "$1") > "$T/aus" 2>&1 || rc=$?
    echo "$rc"
}
# Veröffentlicht (Adresse aus der .env des Servers): weiter bis zur Sperre
[ "$(ENV_URL="$PUB" deploy "$VEROEFFENTLICHT")" = 1 ] || fehler "deploy.sh: unerwarteter Ausgang"
grep -q "Veröffentlicht: ${VEROEFFENTLICHT:0:7}" "$T/aus" || { cat "$T/aus" >&2; fehler "deploy.sh prüfte nicht"; }
grep -q mkdir "$SSH_LOG" || fehler "deploy.sh hielt veröffentlichten Stand an"
# Nicht veröffentlicht: Abbruch vor jeder Änderung auf dem Server
[ "$(ENV_URL="$PUB" deploy "$LOKAL_COMMIT")" = 1 ] || fehler "deploy.sh: unerwarteter Ausgang"
grep -q "nicht enthalten" "$T/aus" || { cat "$T/aus" >&2; fehler "deploy.sh ohne Abbruchgrund"; }
[ "$(wc -l < "$SSH_LOG")" = 1 ] && ! grep -q mkdir "$SSH_LOG" || fehler "deploy.sh änderte trotz Abbruch"
# Ohne Eintrag in der .env: Standardadresse aus docker-compose.server.yml (hier nicht erreichbar)
printf 'services: {}\n# HUBIPLAN_SOURCE_URL: ${HUBIPLAN_SOURCE_URL:-%s}\n' "$T/gibt-es-nicht.git" \
    > "$LOKAL/docker-compose.server.yml"
git -C "$LOKAL" commit -q -am standard
STANDARD=$(git -C "$LOKAL" rev-parse HEAD)
echo "$(git -C "$LOKAL" rev-parse "$STANDARD^{tree}") $STANDARD" >> "$HUBIPLAN_TESTED_FILE"
[ "$(ENV_URL="" deploy "$STANDARD")" = 1 ] || fehler "deploy.sh: unerwarteter Ausgang"
grep -q "gibt-es-nicht.git ist nicht erreichbar" "$T/aus" || { cat "$T/aus" >&2; fehler "Standardadresse nicht genutzt"; }
! grep -q mkdir "$SSH_LOG" || fehler "deploy.sh rollte trotz unerreichbarem Repository aus"
# Testserver-Schalter: Warnung, keine .env-Abfrage, weiter bis zur Sperre
[ "$(HUBIPLAN_UNVEROEFFENTLICHT_ERLAUBT=1 ENV_URL="$PUB" deploy "$LOKAL_COMMIT")" = 1 ] ||
    fehler "deploy.sh: unerwarteter Ausgang"
grep -q WARNUNG "$T/aus" || fehler "deploy.sh ohne Warnung beim Testserver-Schalter"
grep -q mkdir "$SSH_LOG" || fehler "deploy.sh hielt trotz Testserver-Schalter an"
echo "Veröffentlichungsprüfung: veröffentlicht, nicht gepusht, nicht erreichbar, Testserver-Schalter und deploy.sh ok"
