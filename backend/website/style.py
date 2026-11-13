"""Stilregler der Webseite (Webseite › Gestaltung › Feinabstimmung, Konzept webseite-baukasten G1).

Jeder Regler hat 2 oder 3 feste Stufen (Kopfhöhe und Titelbild 4) oder ist ein Schalter.
Gespeichert werden nur verstellte Regler (``Website.style``); fehlt ein Regler, gilt die
Vorgabe des Designs. Die Webseite (hubiplan-website, ``seite/stil.py``) hat dieselbe Liste
und für jede Stufe feste CSS-Regeln; niemand schreibt CSS. Die Namen der Regler und Stufen
stehen in der Oberfläche (StyleTuning.tsx).
"""

from __future__ import annotations

from django.utils.translation import gettext as _

# Regler → Stufen; ``bool`` = Schalter
OPTIONS: dict[str, tuple[str, ...] | type] = {
    # Schrift
    "font": ("system", "modern", "festive"),
    "size": ("normal", "large", "xlarge"),
    "leading": ("tight", "normal", "airy"),
    "headings": ("plain", "line", "color"),
    "heading_align": ("left", "center"),
    "script_greeting": bool,
    # Seite
    "width": ("narrow", "normal", "wide"),
    "background": ("light", "tinted", "grey"),
    "spacing": ("compact", "normal", "generous"),
    "corners": ("square", "slight", "round"),
    # Dunkle Darstellung nach Einstellung des Geräts (Ralf 13.11.2026, Dunkelmodus D2)
    "dark": ("off", "auto"),
    "contrast": bool,
    "to_top": bool,
    # Karten, Bilder, Knöpfe
    "cards": ("border", "shadow", "flat"),
    "images": ("cards", "square"),
    # Seitenverhältnis der Bilder in Kacheln: 3:2, 4:3, quadratisch
    "tile_ratio": ("wide", "classic", "square"),
    "image_frame": bool,
    "buttons": ("filled", "outline"),
    "date": ("tile", "strip"),
    # Kopf und Menü
    "header_bg": ("white", "color", "image"),
    "logo": bool,
    "logo_pos": ("left", "center", "right"),
    "name": bool,
    "header_height": ("low", "medium", "normal", "high"),
    "line": ("none", "thin", "strong"),
    "nav": ("bar", "buttons", "text"),
    "nav_active": ("underline", "filled"),
    "sticky": bool,
    # Menü auf dem Handy: hinter „Menü“ aufklappen oder als Leiste zum Wischen
    "nav_mobile": ("toggle", "scroll"),
    # Startseite
    "hero": ("low", "medium", "normal", "high"),
    "hero_name": bool,
    # Karussell: nicht von selbst, langsam (doppelte Zeit je Bild) oder wie eingestellt
    "carousel": ("off", "slow", "normal"),
    # Fuß
    "footer": ("dark", "light", "color"),
    "footer_align": ("left", "center", "right"),
}

# Was ein Design selbst festlegt (ausgegraut in der Oberfläche, die Webseite übergeht es):
# ``None`` = ganzer Regler, sonst nur diese Stufen. Gleiche Liste in hubiplan-website.
LOCKS: dict[str, dict[str, tuple[str, ...] | None]] = {
    "sidebar": {
        "width": ("narrow",),
        "logo_pos": None,
        "header_height": None,
        "line": None,
        "nav": None,
        "sticky": None,
        "nav_mobile": None,
    },
    "stage": {"width": ("narrow",), "hero_name": None},
    "newspaper": {"nav": None},
}


def catalog() -> dict:
    """Für die Oberfläche: Stufen je Regler und Sperren je Design."""
    return {
        "options": {k: "switch" if v is bool else list(v) for k, v in OPTIONS.items()},
        "locks": {
            design: {k: None if v is None else list(v) for k, v in locks.items()}
            for design, locks in LOCKS.items()
        },
    }


def validate(value) -> dict:
    """Nur bekannte Regler mit bekannten Stufen; ``None`` heißt „wie das Design“.

    Wirft ValueError mit einem Text für die Oberfläche.
    """
    if not isinstance(value, dict):
        raise ValueError(_("Bitte die Stilregler als Zuordnung angeben."))
    result = {}
    for key, given in value.items():
        if key not in OPTIONS:
            raise ValueError(_("Unbekannter Stilregler: {key}").format(key=key))
        if given is None:
            continue
        allowed = OPTIONS[key]
        if allowed is bool:
            if not isinstance(given, bool):
                raise ValueError(_("Bitte {key} als Schalter angeben.").format(key=key))
        elif given not in allowed:
            raise ValueError(_("Unbekannte Stufe für {key}: {value}").format(key=key, value=given))
        result[key] = given
    if result.get("logo") is False and result.get("name") is False:
        raise ValueError(_("Wappen und Vereinsname lassen sich nicht beide ausblenden."))
    return {k: result[k] for k in OPTIONS if k in result}


def public(value) -> dict:
    """Für die öffentliche Schnittstelle: nur gültige Regler (alte Stände ohne Fehler)."""
    try:
        return validate(value or {})
    except ValueError:
        return {}
