#!/usr/bin/env bash
# Sicherheitsprüfung eines Standes mit fremden Werkzeugen (docs/testserver.md,
# „Sicherheitsprüfung“). Ergänzt scripts/test.sh, das schon ruff mit den Sicherheitsregeln,
# pip-audit und npm audit ausführt, um zwei Dinge, die dort fehlen:
#
#   1. Geheimnisse im Stand (gitleaks): Schlüssel, Tokens und Passwörter, die versehentlich
#      eingecheckt wurden. Bewusste Musterwerte stehen in .gitleaks.toml.
#   2. Bekannte Lücken in den Systempaketen der Abbilder (trivy): das gebaute Backend-Abbild
#      und die fremden Abbilder aus den Dockerfiles und docker-compose.server.yml. Bewusst
#      hingenommene Lücken stehen mit Begründung und Datum in .trivyignore.
#
#   scripts/sicherheitspruefung.sh [Git-Referenz] [--nur geheimnisse|abbilder]
#
# Läuft lokal mit Docker, nie auf einem Server. Belegt keinen Testplatz; höchstens
# SICHERHEIT_KERNE (2) Kerne. Braucht Netz (Abbilder und die Lückendatenbank von trivy; die
# Datenbank liegt danach im Docker-Volume hubiplan-trivy-cache). Sie ist keine Freigabe zum
# Ausrollen und gehört nicht zum Merge-Zug: Eine neu bekannt gewordene Lücke in einem
# Basis-Abbild soll keinen fremden Pull Request aufhalten. Gedacht vor jedem Release und nach
# Änderungen an Dockerfiles, Compose-Dateien oder Abhängigkeiten.
#
# Rückgabe: 0 ohne Fund, 1 mit Fund, 2 bei Aufruffehler.
set -euo pipefail

# Werkzeuge mit Digest festgeschrieben wie alle Abbilder (Audit G01)
GITLEAKS="ghcr.io/gitleaks/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f"
TRIVY="ghcr.io/aquasecurity/trivy:0.76.2@sha256:8f6bb947dbc528902e11f2f5be52f7b519f6a39d5d148f41166f2040499768fb"

REF=HEAD
NUR=""
while [ $# -gt 0 ]; do
    case "$1" in
        --nur)
            NUR="${2:-}"
            shift 2 || { echo "Sicherheitsprüfung: --nur braucht geheimnisse oder abbilder." >&2; exit 2; }
            ;;
        -*)
            echo "Sicherheitsprüfung: unbekannte Option $1" >&2
            exit 2
            ;;
        *)
            REF="$1"
            shift
            ;;
    esac
done
case "$NUR" in "" | geheimnisse | abbilder) ;; *)
    echo "Sicherheitsprüfung: --nur kennt geheimnisse und abbilder." >&2
    exit 2
    ;;
esac

cd "$(git rev-parse --show-toplevel)"
COMMIT=$(git rev-parse --verify --quiet "$REF^{commit}") || {
    echo "Sicherheitsprüfung: $REF fehlt." >&2
    exit 2
}
SHA=$(git rev-parse --short "$COMMIT")
docker info > /dev/null 2>&1 || {
    echo "Sicherheitsprüfung: Docker läuft nicht." >&2
    exit 2
}
CPUS="--cpus=${SICHERHEIT_KERNE:-2}"
WORK=$(mktemp -d)
IMG="hubiplan-sicherheit-$$"
aufraeumen() {
    docker image rm -f "$IMG" > /dev/null 2>&1 || true
    rm -rf "$WORK" 2> /dev/null || true
}
trap aufraeumen EXIT
trap 'exit 143' TERM INT HUP
git archive --format=tar "$COMMIT" | tar -x -C "$WORK"
chmod -R a+rX "$WORK"

fehler=0

if [ -z "$NUR" ] || [ "$NUR" = geheimnisse ]; then
    echo "== Geheimnisse im Stand $SHA (gitleaks)"
    # --verbose mit --redact: Funde nennen Datei, Zeile und Regel, nie den Wert
    if docker run --rm "$CPUS" -v "$WORK:/src:ro" "$GITLEAKS" dir /src \
        --config /src/.gitleaks.toml --redact --verbose --no-banner --no-color \
        --max-target-megabytes 5; then
        echo "Geheimnisse: kein Fund"
    else
        echo "Geheimnisse: FUND (oben). Echtes Geheimnis: sofort wechseln, dann entfernen;" >&2
        echo "bewusster Musterwert: in .gitleaks.toml mit Begründung eintragen." >&2
        fehler=1
    fi
fi

if [ -z "$NUR" ] || [ "$NUR" = abbilder ]; then
    echo "== Abbilder im Stand $SHA (trivy)"
    # Der Bau selbst lässt sich nicht auf Kerne begrenzen (lädt vor allem fertige Pakete);
    # wer die Grenze für Tests gerade ausschöpft, startet diesen Teil danach.
    docker build -q -t "$IMG" "$WORK/backend" > /dev/null
    # Fremde Abbilder: letzte Stufe der Dockerfiles (was wirklich läuft) und die Compose-Dienste
    mapfile -t FREMD < <({
        for f in deploy/web.Dockerfile deploy/backup/Dockerfile; do
            grep -oE '^FROM [^ ]+' "$WORK/$f" | tail -1 | cut -d' ' -f2
        done
        grep -oE '^\s+image: [^ ]+@sha256:[0-9a-f]+' "$WORK/docker-compose.server.yml" | awk '{print $2}'
    } | sort -u)
    pruefe() { # Name Abbild [docker-Optionen …]
        local name=$1 bild=$2
        shift 2
        if docker run --rm "$CPUS" -v hubiplan-trivy-cache:/root/.cache "$@" \
            -v "$WORK/.trivyignore:/.trivyignore:ro" "$TRIVY" image --quiet --no-progress \
            --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 \
            --ignorefile /.trivyignore "$bild"; then
            echo "Abbild $name: kein Fund (hoch/kritisch mit verfügbarer Korrektur)"
        else
            echo "Abbild $name: FUND (oben)" >&2
            fehler=1
        fi
    }
    # Das eigene Abbild liegt nur lokal vor: trivy liest es über den Docker-Socket
    pruefe "Backend ($SHA)" "$IMG" -v /var/run/docker.sock:/var/run/docker.sock:ro
    for bild in "${FREMD[@]}"; do
        pruefe "${bild%%@*}" "$bild"
    done
    if [ "$fehler" -ne 0 ]; then
        echo "Abbilder: Basis-Abbild anheben (Dependabot-PR oder Digest von Hand) oder die Lücke" >&2
        echo "mit Begründung und Datum in .trivyignore eintragen, wenn sie HUBIplan nicht betrifft." >&2
    fi
fi

if [ "$fehler" -eq 0 ]; then
    echo "Sicherheitsprüfung: $SHA ohne Fund."
else
    echo "Sicherheitsprüfung: $SHA mit Fund." >&2
fi
exit "$fehler"
