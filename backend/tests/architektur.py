"""Messwerte zur Architektur (docs/architektur.md), ohne Django lauffähig.

``tests/data/architektur_stand.json`` hält als Bestand fest:

- ``rueckwaerts``: Importe gegen die Schichtrichtung (untere Schicht importiert obere).

Der Bestand darf nur kleiner werden. Nach einer Verbesserung neu schreiben::

    python tests/architektur.py --schreiben
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
STAND = Path(__file__).resolve().parent / "data" / "architektur_stand.json"

# Schichten von unten nach oben. Eine Schicht darf nur gleiche und tiefere importieren.
# Alles, was hier nicht steht, ist ein Fachmodul (Schicht 2).
KERN = {"core"}
GRUNDLAGEN = {"access", "accounts", "audit", "organizations"}
# Führen Fachmodule zusammen (Adressen, Schnittstellen nach außen, Datenübernahme)
ZUSAMMENFUEHRUNG = {"config", "datatransfer", "mcpserver", "partnerapi"}


def bereiche() -> list[str]:
    """Alle Django-Apps im Backend (Ordner mit ``__init__.py``), ohne Tests."""
    return sorted(
        p.name
        for p in BACKEND.iterdir()
        if p.is_dir() and (p / "__init__.py").exists() and p.name != "tests"
    )


def schicht(bereich: str) -> int:
    if bereich in KERN:
        return 0
    if bereich in GRUNDLAGEN:
        return 1
    if bereich in ZUSAMMENFUEHRUNG:
        return 3
    return 2


def _dateien(bereich: str):
    for datei in sorted((BACKEND / bereich).rglob("*.py")):
        if "migrations" not in datei.parts:
            yield datei


def importe(bereich: str, alle: set[str]) -> set[str]:
    """Andere Bereiche, die ``bereich`` importiert (auch innerhalb von Funktionen)."""
    ziele: set[str] = set()
    for datei in _dateien(bereich):
        for knoten in ast.walk(ast.parse(datei.read_text(encoding="utf-8"))):
            if isinstance(knoten, ast.ImportFrom):
                namen = [knoten.module] if knoten.level == 0 and knoten.module else []
            elif isinstance(knoten, ast.Import):
                namen = [n.name for n in knoten.names]
            else:
                continue
            ziele.update(n.split(".")[0] for n in namen)
    return (ziele & alle) - {bereich}


def rueckwaerts() -> list[str]:
    """Importe gegen die Schichtrichtung, als sortierte Liste ``"von -> nach"``."""
    alle = set(bereiche())
    return sorted(
        f"{von} -> {nach}"
        for von in alle
        for nach in importe(von, alle)
        if schicht(von) < schicht(nach)
    )


def messen() -> dict:
    return {"rueckwaerts": rueckwaerts()}


def bestand() -> dict:
    return json.loads(STAND.read_text(encoding="utf-8"))


if __name__ == "__main__":
    if "--schreiben" in sys.argv:
        STAND.write_text(
            json.dumps(messen(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"geschrieben: {STAND}")
    else:
        print(json.dumps(messen(), indent=2, ensure_ascii=False))
