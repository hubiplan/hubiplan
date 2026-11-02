#!/usr/bin/env bash
# Releases von HUBIplan und der Webseite (docs/releases.md):
#   scripts/release.sh entwurf [Ref]   Änderungshinweise seit dem letzten Release eintragen
#   scripts/release.sh taggen  [Ref]   prüfen, Tag und GitHub-Release anlegen (nur auf Ralfs Wort)
# Für die Webseite im Klon von hubiplan-website aufrufen: ~/hubiplan/scripts/release.sh …
# Braucht git, python3 und gh (GH=… für einen anderen Pfad, z. B. gh.exe unter WSL).
set -euo pipefail
exec python3 "$(dirname "$(readlink -f "$0")")/release.py" "$@"
