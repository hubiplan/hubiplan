#!/usr/bin/env bash
# Schreibt die Python-Abhängigkeiten mit Prüfsummen fest (Gesamtaudit 11.11., H-02).
#
# Von Hand gepflegt werden nur backend/requirements.in (Betrieb) und
# backend/requirements-dev.in (Tests). Daraus entstehen requirements.txt und
# requirements-dev.txt mit allen indirekten Abhängigkeiten und ihren sha256-Prüfsummen.
# Das Docker-Image installiert nur diese Dateien (pip --require-hashes --no-deps).
#
# Aufruf nach jeder Änderung an einer .in-Datei:   scripts/pakete-sperren.sh
# Einzelnes Paket anheben (z. B. Sicherheitsupdate): scripts/pakete-sperren.sh -P django
#
# Läuft im selben Python-Basis-Image wie der Server, damit Umgebungsmarker passen.
set -euo pipefail
cd "$(dirname "$0")/../backend"
BASE=$(grep -m1 -oE '^FROM python:[^ ]+' Dockerfile | cut -d' ' -f2)
docker run --rm -v "$PWD:/w" -w /w -u "$(id -u):$(id -g)" -e HOME=/tmp "$BASE" sh -c "
    set -e
    pip install -q --user pip-tools==7.6.2
    export PATH=/tmp/.local/bin:\$PATH
    opts='-q --generate-hashes --allow-unsafe --strip-extras --no-emit-index-url'
    pip-compile \$opts $* -o requirements.txt requirements.in
    pip-compile \$opts $* -o requirements-dev.txt requirements-dev.in
"
echo "requirements.txt und requirements-dev.txt neu geschrieben."
