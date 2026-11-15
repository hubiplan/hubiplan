"""Name im Briefkopf: Schriftgröße und Umbruch für Word und PDF gleich (Issue #487).

Ohne eigenen „Namen im Briefkopf“ wird der Name der Einheit auf eine Zeile verkleinert, aber
nicht unter ``MIN_ONE_LINE``. Passt er dann noch nicht, wird er ausgewogen auf zwei Zeilen
umbrochen, damit kein einzelnes Wort allein in der zweiten Zeile steht. Mit eigenem Namen
bestimmt die Einheit den Umbruch selbst (höchstens zwei Zeilen, die zweite wahlweise kleiner).

Gemessen wird mit den Schriftmaßen, die auch das PDF nutzt (Webschriften eingebettet, Office-
Schriften als Helvetica bzw. Times). Word bekommt dieselben Größen mit etwas Reserve.
"""

from __future__ import annotations

from dataclasses import dataclass

from reportlab.pdfbase.pdfmetrics import stringWidth

from .typefaces import pdf_fonts

NAME_SIZE = 16.0  # pt, wie bisher
LONG_NAME_SIZE = 13.0  # pt ab LONG_NAME Zeichen, wie bisher
LONG_NAME = 45
MIN_ONE_LINE = 11.0  # pt: kleiner wird der Name nicht, lieber zwei Zeilen
MIN_SIZE = 7.0  # pt: Untergrenze für jede Zeile
SMALL_SHARE = 0.7  # zweite Zeile „kleiner“
MAX_LINES = 2
WORD_RESERVE = 0.95  # Word misst mit der echten Schrift etwas anders


@dataclass(frozen=True)
class HeadLine:
    text: str
    size: float


def own_lines(value: str | None) -> list[str]:
    """Zeilen des eigenen Namens im Briefkopf, ohne leere Zeilen."""
    return [line.strip() for line in (value or "").splitlines() if line.strip()][:MAX_LINES]


def _width(text: str, face: str, size: float) -> float:
    return stringWidth(text, face, size)


def _fit(text: str, face: str, size: float, width: float, minimum: float) -> float:
    while size > minimum and _width(text, face, size) > width:
        size -= 0.5
    return size


def _half(size: float) -> float:
    return round(size * 2) / 2


def balanced(text: str, face: str, size: float) -> tuple[str, str] | None:
    """Zwei Zeilen mit möglichst gleicher Breite; None, wenn es nur ein Wort ist."""
    words = text.split()
    if len(words) < 2:
        return None
    best: tuple[float, str, str] | None = None
    for i in range(1, len(words)):
        first, second = " ".join(words[:i]), " ".join(words[i:])
        widest = max(_width(first, face, size), _width(second, face, size))
        if best is None or widest < best[0]:
            best = (widest, first, second)
    return (best[1], best[2]) if best else None


def base_size(lines: list[str]) -> float:
    return NAME_SIZE if max(len(line) for line in lines) < LONG_NAME else LONG_NAME_SIZE


def head_lines(
    name: str,
    own: str | None,
    font: str,
    width_mm: float,
    *,
    small_second: bool = False,
    reserve: float = 1.0,
) -> list[HeadLine]:
    """Zeilen des Namens im Briefkopf mit Schriftgröße in pt für ``width_mm`` Breite."""
    _regular, face = pdf_fonts(font)
    width = width_mm / 25.4 * 72 * reserve
    lines = own_lines(own)
    if lines:
        base = base_size(lines)
        if len(lines) == 2 and small_second:
            first = _fit(lines[0], face, base, width, MIN_SIZE)
            second = _fit(
                lines[1], face, max(_half(first * SMALL_SHARE), MIN_SIZE), width, MIN_SIZE
            )
            return [HeadLine(lines[0], first), HeadLine(lines[1], second)]
        size = min(_fit(line, face, base, width, MIN_SIZE) for line in lines)
        return [HeadLine(line, size) for line in lines]
    name = " ".join(name.split())
    base = base_size([name])
    size = _fit(name, face, base, width, MIN_ONE_LINE)
    if _width(name, face, size) <= width:
        return [HeadLine(name, size)]
    split = balanced(name, face, base)
    if split is None:
        return [HeadLine(name, _fit(name, face, base, width, 5))]
    size = min(_fit(part, face, base, width, MIN_SIZE) for part in split)
    return [HeadLine(part, size) for part in split]
