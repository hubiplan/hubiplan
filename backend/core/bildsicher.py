"""Pillow ohne PostScript (Gesamtaudit 15.11., PUB-01).

Pillow übergibt EPS-Dateien beim Laden an Ghostscript. Ghostscript ist im Backend-Abbild für
PDF/A (billing/hybrid.py) installiert, läuft dort aber ohne Zeitgrenze, und Lücken in seinem
-dSAFER-Modus erlauben Codeausführung. Hochgeladene Bilder (Unterschrift im Briefbogen, Logos
aus dem Verbund) sollen deshalb nie als EPS geöffnet werden: Das Format wird beim Start aus der
Liste der Formate entfernt, die ``Image.open`` erkennt. Die einzelnen Aufrufer prüfen das Format
zusätzlich selbst (``IMAGE_FORMATS``).
"""

from __future__ import annotations

# Formate für hochgeladene Bilder, die nicht schon anderswo geprüft werden
IMAGE_FORMATS = ("PNG", "JPEG", "WEBP", "GIF", "BMP")
GESPERRT = ("EPS",)


def install() -> None:
    from PIL import Image

    Image.init()
    for fmt in GESPERRT:
        Image.OPEN.pop(fmt, None)
        while fmt in Image.ID:
            Image.ID.remove(fmt)
