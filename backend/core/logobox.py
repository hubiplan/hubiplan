"""Größe eines Logos in einem Kasten (hubiplan #527).

Logos waren in PDFs auf ein Quadrat eingepasst; ein Schriftzug im Querformat (etwa 3 : 1) wurde
dadurch sehr klein. Jetzt ist die Höhe des Kastens fest und die Breite folgt dem Bild bis zu
einer Obergrenze. Quadratische Wappen sehen aus wie bisher.
"""

from __future__ import annotations

from reportlab.lib.utils import ImageReader


def logo_size(source, max_w: float, max_h: float) -> tuple[float, float]:
    """(Breite, Höhe) des Logos im Kasten ``max_w`` × ``max_h``, Seitenverhältnis bleibt.
    ``source``: Pfad, Datei oder ``ImageReader``. Lässt sich das Bild nicht lesen, das Quadrat
    wie bisher (``max_h`` × ``max_h``, höchstens ``max_w`` breit)."""
    side = min(max_w, max_h)
    try:
        reader = source if hasattr(source, "getSize") else ImageReader(source)
        w, h = reader.getSize()
    except Exception:  # noqa: BLE001 – beschädigtes Bild: Quadrat wie bisher
        return side, side
    if not w or not h or w <= 0 or h <= 0:
        return side, side
    scale = min(max_w / w, max_h / h)
    return w * scale, h * scale
