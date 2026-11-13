"""Farben, Kontrastprüfung (WCAG 2.x) und Vererbung des Erscheinungsbilds."""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

# Standard der Plattform, falls nirgends etwas gesetzt ist (Hubi-Grün, Hubi-Gold)
DEFAULT_PRIMARY = "#0e7c66"
DEFAULT_ACCENT = "#f2b33d"

DARK_TEXT = "#1d2421"
LIGHT_TEXT = "#ffffff"
SURFACE = "#ffffff"

# Mindestkontraste: Text auf Farbflächen (normaler Text) und Primärfarbe als
# Linkfarbe/Rahmen auf weißem Hintergrund (Bedienelemente)
MIN_TEXT_CONTRAST = 4.5
MIN_UI_CONTRAST = 3.0


def _channel(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def text_color_on(background: str) -> str:
    """Besser lesbare Schriftfarbe (hell oder dunkel) auf einer Farbfläche."""
    if contrast(background, LIGHT_TEXT) >= contrast(background, DARK_TEXT):
        return LIGHT_TEXT
    return DARK_TEXT


def validate_hex_color(value: str) -> None:
    if not HEX_COLOR.match(value or ""):
        raise ValidationError(gettext("Bitte eine Farbe im Format #RRGGBB angeben."))


def check_primary(color: str) -> list[str]:
    problems = []
    if contrast(color, text_color_on(color)) < MIN_TEXT_CONTRAST:
        problems.append(gettext("Text auf der Primärfarbe wäre schlecht lesbar."))
    if contrast(color, SURFACE) < MIN_UI_CONTRAST:
        problems.append(
            gettext("Die Primärfarbe ist auf weißem Hintergrund zu hell (Rahmen und Symbole).")
        )
    return problems


def check_accent(color: str) -> list[str]:
    if contrast(color, text_color_on(color)) < MIN_TEXT_CONTRAST:
        return [gettext("Text auf der Akzentfarbe wäre schlecht lesbar.")]
    return []


# Weitere Farben neben Haupt- und Zweitfarbe (Palette höchstens sechs Farben)
MAX_EXTRA_COLORS = 4
MAX_COLOR_NAME = 30
# Wofür eine Farbe da ist (Ralf 10.11.2026, Farbblatt), z. B. „Fließtext“
MAX_COLOR_USE = 60
# Benannte Verläufe aus zwei Palettenfarben (Ralf 10.11.2026)
MAX_GRADIENTS = 2
GRADIENT_DIRECTIONS = ("right", "down")


def clean_extra_colors(value) -> list[dict]:
    """Weitere Farben prüfen: Liste von {color, name}, Text darauf muss lesbar sein."""
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValidationError(gettext("Weitere Farben bitte als Liste angeben."))
    if len(value) > MAX_EXTRA_COLORS:
        raise ValidationError(
            gettext("Höchstens {MAX_EXTRA_COLORS} weitere Farben (zusammen sechs).").format(
                MAX_EXTRA_COLORS=MAX_EXTRA_COLORS
            )
        )
    result = []
    for i, item in enumerate(value, start=3):
        if not isinstance(item, dict):
            raise ValidationError(gettext("Weitere Farben bitte als Liste angeben."))
        color = str(item.get("color") or "").lower()
        validate_hex_color(color)
        if contrast(color, text_color_on(color)) < MIN_TEXT_CONTRAST:
            raise ValidationError(
                gettext("Text auf der {i}. Farbe wäre schlecht lesbar.").format(i=i)
            )
        name = _short_text(item.get("name"), MAX_COLOR_NAME)
        use = _short_text(item.get("use"), MAX_COLOR_USE)
        entry = {"color": color, "name": name}
        if use:
            entry["use"] = use
        result.append(entry)
    return result


def _short_text(value, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    if limit == MAX_COLOR_NAME:
        message = gettext("Farbnamen bitte höchstens {MAX_COLOR_NAME} Zeichen.").format(
            MAX_COLOR_NAME=MAX_COLOR_NAME
        )
    else:
        message = gettext("Die Verwendung bitte höchstens {limit} Zeichen.").format(limit=limit)
    raise ValidationError(message)


def clean_color_use(value) -> str:
    """Verwendung einer Farbe (Freitext, kurz)."""
    return _short_text(value, MAX_COLOR_USE)


def clean_gradients(value) -> list[dict]:
    """Verläufe prüfen: Liste von {name, from, to, direction}; from/to sind Palettenplätze."""
    if value in (None, ""):
        return []
    message = gettext("Verläufe bitte als Liste angeben.")
    if not isinstance(value, list):
        raise ValidationError(message)
    if len(value) > MAX_GRADIENTS:
        raise ValidationError(
            gettext("Höchstens {MAX_GRADIENTS} Verläufe.").format(MAX_GRADIENTS=MAX_GRADIENTS)
        )
    result = []
    for item in value:
        if not isinstance(item, dict):
            raise ValidationError(message)
        start, end = item.get("from"), item.get("to")
        slots = range(2 + MAX_EXTRA_COLORS)
        if not all(
            isinstance(v, int) and not isinstance(v, bool) and v in slots for v in (start, end)
        ):
            raise ValidationError(gettext("Ein Verlauf braucht zwei Farben aus der Palette."))
        if start == end:
            raise ValidationError(gettext("Ein Verlauf braucht zwei verschiedene Farben."))
        direction = item.get("direction") or "right"
        if direction not in GRADIENT_DIRECTIONS:
            raise ValidationError(gettext("Diese Richtung gibt es nicht."))
        result.append(
            {
                "name": _short_text(item.get("name"), MAX_COLOR_NAME),
                "from": start,
                "to": end,
                "direction": direction,
            }
        )
    return result


# Wofür eine Palettenfarbe da ist (Ralf 13.11.2026); jede Rolle hat höchstens eine Farbe
PALETTE_ROLES = ("text", "muted", "surface", "background")


def clean_palette_roles(value) -> dict:
    """Farbrollen prüfen: {rolle: platz}, Platz 0 = Hauptfarbe, 1 = Zweitfarbe, 2 … weitere."""
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ValidationError(gettext("Farbrollen bitte als Zuordnung angeben."))
    result = {}
    for role, slot in value.items():
        if role not in PALETTE_ROLES:
            raise ValidationError(gettext("Diese Farbrolle gibt es nicht."))
        if slot is None:
            continue
        if isinstance(slot, bool) or not isinstance(slot, int):
            raise ValidationError(gettext("Eine Farbrolle braucht eine Farbe aus der Palette."))
        if not 0 <= slot < 2 + MAX_EXTRA_COLORS:
            raise ValidationError(gettext("Eine Farbrolle braucht eine Farbe aus der Palette."))
        result[role] = slot
    return result


def resolve_palette_roles(stored, palette: list[dict]) -> dict:
    """Gespeicherte Farbrollen, deren Platz es in der Palette gibt: {rolle: platz}."""
    if not isinstance(stored, dict):
        return {}
    return {
        role: slot
        for role, slot in stored.items()
        if role in PALETTE_ROLES
        and isinstance(slot, int)
        and not isinstance(slot, bool)
        and 0 <= slot < len(palette)
    }


def text_color_on_pair(a: str, b: str) -> str:
    """Schriftfarbe, die auf beiden Enden eines Verlaufs am besten lesbar ist."""
    light = min(contrast(a, LIGHT_TEXT), contrast(b, LIGHT_TEXT))
    dark = min(contrast(a, DARK_TEXT), contrast(b, DARK_TEXT))
    return LIGHT_TEXT if light >= dark else DARK_TEXT


def resolve_gradients(stored, palette: list[dict]) -> list[dict]:
    """Gespeicherte Verläufe mit den Farben der Palette; fehlt ein Platz, entfällt der Verlauf."""
    result = []
    for item in stored or []:
        if not isinstance(item, dict):
            continue
        start, end = item.get("from"), item.get("to")
        if not (isinstance(start, int) and isinstance(end, int)):
            continue
        if not (0 <= start < len(palette) and 0 <= end < len(palette)):
            continue
        a, b = palette[start]["color"], palette[end]["color"]
        on = text_color_on_pair(a, b)
        result.append(
            {
                "name": str(item.get("name") or ""),
                "from": start,
                "to": end,
                "direction": item.get("direction")
                if item.get("direction") in GRADIENT_DIRECTIONS
                else "right",
                "colors": [a, b],
                "on_color": on,
                "contrast": round(min(contrast(a, on), contrast(b, on)), 2),
            }
        )
    return result[:MAX_GRADIENTS]


def _entry(color: str, name: str, use: str = "") -> dict:
    return {"color": color, "on_color": text_color_on(color), "name": name or "", "use": use or ""}


def effective_theme(chain: list) -> dict:
    """Erscheinungsbild aus einer Kette vom Speziellsten zum Allgemeinsten.

    Jedes Glied hat ``primary_color``, ``accent_color``, ``logo`` und ``logo_dark``; das erste
    gesetzte gewinnt (Abteilung ← Verein ← Dachverband ← Plattform).
    """

    def first(attr: str):
        for item in chain:
            value = getattr(item, attr, None)
            if value:
                return value, item
        return None, None

    primary, primary_src = first("primary_color")
    accent, _ = first("accent_color")
    logo, logo_src = first("logo")
    # Logo für den Dunkelmodus (Ralf 10.11.2026): von der ersten Ebene mit einem der beiden
    # Logos; hat sie kein dunkles, gilt dort ihr helles. Das helle Logo erbt wie bisher.
    dark_src = next(
        (o for o in chain if getattr(o, "logo", None) or getattr(o, "logo_dark", None)), None
    )
    logo_dark = None
    if dark_src is not None:
        logo_dark = getattr(dark_src, "logo_dark", None) or getattr(dark_src, "logo", None)
    primary = primary or DEFAULT_PRIMARY
    accent = accent or DEFAULT_ACCENT
    # Palette erbt als Ganzes mit der Hauptfarbe (Ralf 2026-10-31): Namen und weitere
    # Farben kommen von der Ebene, die die Hauptfarbe festlegt
    palette = [
        _entry(
            primary,
            getattr(primary_src, "primary_color_name", ""),
            getattr(primary_src, "primary_color_use", ""),
        ),
        _entry(
            accent,
            getattr(primary_src, "accent_color_name", ""),
            getattr(primary_src, "accent_color_use", ""),
        ),
    ]
    for item in getattr(primary_src, "extra_colors", None) or []:
        color = item.get("color") if isinstance(item, dict) else None
        if color and HEX_COLOR.match(color):
            palette.append(_entry(color.lower(), item.get("name", ""), item.get("use", "")))
    palette = palette[: 2 + MAX_EXTRA_COLORS]
    roles = resolve_palette_roles(getattr(primary_src, "palette_roles", None), palette)
    return {
        "primary": primary,
        "on_primary": text_color_on(primary),
        "accent": accent,
        "on_accent": text_color_on(accent),
        "logo_url": logo.url if logo else None,
        "logo_dark_url": logo_dark.url if logo_dark else None,
        "palette": palette,
        # Verläufe erben wie die Palette mit der Hauptfarbe
        "gradients": resolve_gradients(getattr(primary_src, "gradients", None), palette),
        # Farbrollen erben ebenso; die Oberfläche rechnet daraus im hellen Modus Text,
        # Flächen und Hintergrund (theme.ts appColors), nur wenn palette_roles_in_app
        "palette_roles": roles,
        "palette_roles_in_app": bool(roles)
        and bool(getattr(primary_src, "palette_roles_in_app", False)),
        "inherited_from": {
            "colors": getattr(primary_src, "name", None),
            "logo": getattr(logo_src, "name", None),
        },
    }
