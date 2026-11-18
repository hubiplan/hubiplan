#!/usr/bin/env bash
# Prüft, ob ein Commit im öffentlichen Repository enthalten ist (AGPL § 13, Gesamtaudit
# 15.11., OPS-13): Die Seite /lizenz verlinkt den Quellcode genau der laufenden Fassung
# (HUBIPLAN_SOURCE_URL + Commit). Kennt das öffentliche Repository den Commit nicht, zeigt
# der Link ins Leere und für den laufenden Dienst ist kein Quellcode angeboten.
#
# Wird von deploy/deploy.sh eingebunden; einzeln aufrufbar (z. B. für Tests):
#   deploy/veroeffentlicht.sh <repo-ordner> <commit> <öffentliche-url>
#
# Veröffentlicht heißt: Der Commit ist von einem Branch oder Tag des öffentlichen
# Repositorys aus erreichbar. Geholt wird in ein Wegwerf-Repository, das die Objekte des
# lokalen Repositorys mitbenutzt; das lokale Repository bekommt keine neuen Referenzen.
# Ist das öffentliche Repository nicht erreichbar, gilt der Commit NICHT als veröffentlicht.
#
# Nur für reine Testserver: HUBIPLAN_UNVEROEFFENTLICHT_ERLAUBT=1 überspringt die Prüfung
# (mit Warnung). Auf Servern, die andere als das Entwicklerteam nutzen, nie setzen.

# veroeffentlicht_pruefen <repo-ordner> <commit> <öffentliche-url>
# Rückgabe 0: veröffentlicht (oder Prüfung ausdrücklich übersprungen); 1: nicht veröffentlicht;
# 2: öffentliches Repository nicht erreichbar oder Angaben unbrauchbar.
veroeffentlicht_pruefen() {
    local repo="$1" commit="$2" url="$3" kurz objekte tmp treffer zeit=()
    if [ "${HUBIPLAN_UNVEROEFFENTLICHT_ERLAUBT:-}" = 1 ]; then
        {
            echo "WARNUNG: HUBIPLAN_UNVEROEFFENTLICHT_ERLAUBT=1 – Prüfung auf Veröffentlichung übersprungen."
            echo "  Nur für reine Testserver mit erfundenen Daten. Der Quellcode-Link auf /lizenz"
            echo "  zeigt dann auf einen Stand, den das öffentliche Repository womöglich nicht kennt;"
            echo "  das Quellcode-Angebot nach AGPL § 13 passt so nicht zur laufenden Fassung."
            echo "  Den Stand bald veröffentlichen (pushen) oder einen veröffentlichten ausrollen."
        } >&2
        return 0
    fi
    case "$url" in
        "" | -*)
            echo "Abbruch: Keine gültige Adresse des öffentlichen Repositorys („$url“)." >&2
            return 2
            ;;
    esac
    if ! commit=$(git -C "$repo" rev-parse -q --verify "$commit^{commit}"); then
        echo "Abbruch: Commit „$2“ ist im lokalen Repository unbekannt." >&2
        return 2
    fi
    kurz="${commit:0:7}"
    if ! objekte=$(cd "$repo" && cd "$(git rev-parse --git-common-dir)/objects" && pwd -P); then
        echo "Abbruch: Objektordner des lokalen Repositorys nicht gefunden." >&2
        return 2
    fi
    # Git für Windows versteht MSYS-Pfade („/e/…“) in alternates nicht
    if command -v cygpath > /dev/null 2>&1; then
        objekte=$(cygpath -m "$objekte") || return 2
    fi
    tmp=$(mktemp -d) || return 2
    # Wegwerf-Repository nur für diese Prüfung; die Objekte des lokalen Repositorys
    # mitbenutzen (alternates), damit nur Fehlendes übertragen wird.
    if ! git init -q --bare "$tmp/oeffentlich.git" ||
        ! echo "$objekte" > "$tmp/oeffentlich.git/objects/info/alternates"; then
        rm -rf "$tmp"
        echo "Abbruch: Prüf-Repository für die Veröffentlichung nicht angelegt." >&2
        return 2
    fi
    if command -v timeout > /dev/null 2>&1; then
        zeit=(timeout "${HUBIPLAN_VEROEFFENTLICHT_TIMEOUT:-180}")
    fi
    # Nie nach Zugangsdaten fragen; ext:: und ähnliche Transporte nicht zulassen.
    if ! GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/false SSH_ASKPASS=/bin/false \
        GIT_ALLOW_PROTOCOL="${GIT_ALLOW_PROTOCOL:-https:ssh:git:file}" \
        "${zeit[@]}" git -C "$tmp/oeffentlich.git" fetch -q --no-tags "$url" \
        '+refs/heads/*:refs/heads/*' '+refs/tags/*:refs/tags/*' < /dev/null; then
        rm -rf "$tmp"
        {
            echo "Abbruch: Das öffentliche Repository $url ist nicht erreichbar oder nicht lesbar."
            echo "  Ohne Abgleich gilt $kurz nicht als veröffentlicht; nichts ausgerollt."
            echo "  Netz/Adresse prüfen (HUBIPLAN_SOURCE_URL) und erneut versuchen."
        } >&2
        return 2
    fi
    if ! treffer=$(git -C "$tmp/oeffentlich.git" for-each-ref --count=1 --format='%(refname)' \
        --contains "$commit" refs/heads refs/tags 2> /dev/null); then
        rm -rf "$tmp"
        echo "Abbruch: Abgleich von $kurz mit $url fehlgeschlagen; nichts ausgerollt." >&2
        return 2
    fi
    rm -rf "$tmp"
    if [ -z "$treffer" ]; then
        {
            echo "Abbruch: $kurz ist im öffentlichen Repository $url nicht enthalten."
            echo "  Die Seite /lizenz würde auf einen unbekannten Stand verlinken (AGPL § 13)."
            echo "  Erst den Branch oder Tag dorthin pushen, dann ausrollen."
            echo "  Nur für reine Testserver: HUBIPLAN_UNVEROEFFENTLICHT_ERLAUBT=1 (siehe docs/betrieb.md)."
        } >&2
        return 1
    fi
    echo "Veröffentlicht: $kurz ist in $url enthalten (${treffer#refs/})."
    return 0
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    set -euo pipefail
    if [ $# -ne 3 ]; then
        echo "Aufruf: deploy/veroeffentlicht.sh <repo-ordner> <commit> <öffentliche-url>" >&2
        exit 2
    fi
    rc=0
    veroeffentlicht_pruefen "$@" || rc=$?
    exit "$rc"
fi
