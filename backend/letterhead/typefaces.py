"""Schriften des Briefbogens im PDF und in Word (Issue #470).

Die Office-Schriften (Arial, Georgia …) stehen im PDF als Helvetica bzw. Times, so wie bisher.
Die Schriften der Webseite liegen als TTF in ``fonts/`` (SIL OFL 1.1) und werden ins PDF
eingebettet. In Word steht ihr Name mit einer Ersatzschrift, weil sie nicht überall installiert
sind.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent / "fonts"

SERIF = {"Cambria", "Georgia", "Times New Roman"}

# Name → (Dateistamm, Gattung für Word, Datei für fett oder None)
WEB_FONTS: dict[str, tuple[str, str, bool]] = {
    "Source Sans 3": ("source-sans-3", "swiss", True),
    "Crimson Pro": ("crimson-pro", "roman", True),
    "Atkinson Hyperlegible": ("atkinson-hyperlegible", "swiss", True),
    "Open Sans": ("open-sans", "swiss", True),
    "Roboto": ("roboto", "swiss", True),
    "Oswald": ("oswald", "swiss", True),
    "UnifrakturMaguntia": ("unifraktur-maguntia", "decorative", False),
}


def is_web_font(name: str) -> bool:
    return name in WEB_FONTS


@cache
def _register(name: str) -> tuple[str, str]:
    from reportlab.lib.fonts import addMapping
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    stem, _family, has_bold = WEB_FONTS[name]
    regular = f"HP-{stem}"
    bold = f"HP-{stem}-bold" if has_bold else regular
    pdfmetrics.registerFont(TTFont(regular, str(FONT_DIR / f"{stem}-400.ttf")))
    if has_bold:
        pdfmetrics.registerFont(TTFont(bold, str(FONT_DIR / f"{stem}-700.ttf")))
    # <b> in Absätzen findet so den fetten Schnitt
    addMapping(regular, 0, 0, regular)
    addMapping(regular, 1, 0, bold)
    addMapping(regular, 0, 1, regular)
    addMapping(regular, 1, 1, bold)
    if has_bold:
        addMapping(bold, 0, 0, regular)
        addMapping(bold, 1, 0, bold)
        addMapping(bold, 0, 1, regular)
        addMapping(bold, 1, 1, bold)
    return regular, bold


def pdf_fonts(name: str) -> tuple[str, str]:
    """(normal, fett) für reportlab: Webschrift eingebettet, sonst Helvetica bzw. Times."""
    if name in WEB_FONTS:
        try:
            return _register(name)
        except Exception:  # noqa: BLE001 – fehlende Datei: lieber Standardschrift als kein Brief
            return "Helvetica", "Helvetica-Bold"
    if name in SERIF:
        return "Times-Roman", "Times-Bold"
    return "Helvetica", "Helvetica-Bold"


def word_family(name: str) -> str:
    """Schriftgattung für die Schrifttabelle in Word (hilft bei der Ersetzung)."""
    if name in WEB_FONTS:
        return WEB_FONTS[name][1]
    return "roman" if name in SERIF else "swiss"
