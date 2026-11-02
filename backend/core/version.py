"""Versionsnummer der laufenden Fassung (docs/releases.md).

deploy/server-setup.sh legt sie beim Ausrollen als ``hubiplan_version.txt`` neben
``manage.py`` ab, bevor das Image gebaut wird: ``2026.11.0`` für ein Release,
``2026.11.0+3.0a5d21e`` für einen Stand danach, sonst nur der Commit. In der Entwicklung
und in Tests fehlt die Datei; dann ist die Version leer.
"""

from functools import cache
from pathlib import Path

VERSION_FILE = Path(__file__).resolve().parent.parent / "hubiplan_version.txt"


@cache
def running_version() -> str:
    try:
        text = VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    # Nur die Zeichen, die deploy.sh erzeugt (Ziffern, Buchstaben, Punkt, Plus)
    erlaubt = all((c.isascii() and c.isalnum()) or c in ".+" for c in text)
    if not text or len(text) > 40 or not erlaubt:
        return ""
    return text
