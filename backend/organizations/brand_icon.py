"""Symbol der Instanz (White Label W2): Browser-Tab, Handy-Startbildschirm, PWA.

Der Betreiber lädt ein Bild hoch; HUBIplan prüft es wie ein Logo, macht es quadratisch
(durchsichtiger Rand) und speichert es in 512 × 512 Pixeln. Die einzelnen Größen
entstehen beim Abruf aus dieser Datei und werden im Speicher gehalten.
"""

from __future__ import annotations

import io
from functools import lru_cache

from django.core.exceptions import ValidationError
from django.utils.translation import gettext
from PIL import Image

from core.filecheck import clean_logo

ICON_SIDE = 512
# Mindestgröße der längeren Seite, damit das Symbol auf dem Handy nicht verschwimmt
MIN_SIDE = 512
# Größen, die Browser und Handys abholen (favicon, Apple, Android/PWA)
SIZES = (32, 180, 192, 512)
# Maskierbares Symbol: Android schneidet bis zu 20 % weg (Kreis); Inhalt in die Mitte
MASKABLE_CONTENT = 0.8
BACKGROUND = (255, 255, 255, 255)


def clean_icon(content: bytes, *, remove_background: bool = False) -> bytes:
    """Bild prüfen und als quadratisches PNG (512 px, durchsichtiger Rand) zurückgeben."""
    data = clean_logo(content, remove_background=remove_background)
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    if max(img.size) < MIN_SIDE:
        raise ValidationError(
            gettext("Das Symbol braucht mindestens {px} Pixel Breite oder Höhe.").format(
                px=MIN_SIDE
            )
        )
    return _square(img)


def _square(img: Image.Image) -> bytes:
    side = max(img.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(img, ((side - img.width) // 2, (side - img.height) // 2), img)
    square = square.resize((ICON_SIDE, ICON_SIDE), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    square.save(buf, "PNG", optimize=True)
    return buf.getvalue()


@lru_cache(maxsize=16)
def square(content: bytes) -> bytes:
    """Gespeichertes Wappen quadratisch (durchsichtiger Rand) als Ersatz für ein Symbol (W7).

    Ohne Mindestgröße: Ein kleines Wappen ist auf dem Handy besser als ein fremdes Zeichen.
    """
    return _square(Image.open(io.BytesIO(content)).convert("RGBA"))


@lru_cache(maxsize=16)
def render(name: str, content: bytes, size: int, *, maskable: bool = False) -> bytes:
    """Eine Größe des Symbols. name dient nur als Schlüssel (neue Datei = neuer Name).

    Apple-Symbol (180) und maskierbares Symbol bekommen einen weißen Hintergrund, weil
    iOS und Android durchsichtige Flächen sonst schwarz füllen.
    """
    img = Image.open(io.BytesIO(content)).convert("RGBA")
    if maskable:
        inner = round(size * MASKABLE_CONTENT)
        canvas = Image.new("RGBA", (size, size), BACKGROUND)
        icon = img.resize((inner, inner), Image.Resampling.LANCZOS)
        canvas.paste(icon, ((size - inner) // 2, (size - inner) // 2), icon)
    else:
        canvas = img.resize((size, size), Image.Resampling.LANCZOS)
        if size == 180:
            flat = Image.new("RGBA", (size, size), BACKGROUND)
            flat.alpha_composite(canvas)
            canvas = flat.convert("RGB")
    buf = io.BytesIO()
    canvas.save(buf, "PNG", optimize=True)
    full = buf.getvalue()
    # Mit Farbpalette meist ein Viertel so groß, sichtbar gleich (Ladezeiten der
    # Vereinswebseite 14.11.); nur nehmen, wenn es wirklich kleiner ist
    method = Image.Quantize.FASTOCTREE if canvas.mode == "RGBA" else Image.Quantize.MEDIANCUT
    small = io.BytesIO()
    canvas.quantize(colors=256, method=method).save(small, "PNG", optimize=True)
    return small.getvalue() if small.tell() < len(full) else full
