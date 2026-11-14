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
    # Webseite #75: „Start“ in der Menüleiste am Bildschirm (Logo und Kopfbild führen zur
    # Startseite, im Handymenü bleibt er) und Lage der Suche (aus: Baustein „Suche“)
    "nav_start": bool,
    "search": ("nav", "header", "footer"),
    # Startseite
    "hero": ("low", "medium", "normal", "high"),
    "hero_name": bool,
    # Karussell: nicht von selbst, langsam (doppelte Zeit je Bild) oder wie eingestellt
    "carousel": ("off", "slow", "normal"),
    # Ralf 14.11.2026: Titelbild abdunkeln oder halb durchsichtig in Vereinsfarbe färben,
    # Bildausschnitt und Lage des Namens auf dem Bild
    "hero_shade": ("none", "light", "strong"),
    "hero_tint": ("dark", "primary", "accent"),
    "hero_focus": ("top", "center", "bottom"),
    "hero_text": ("top", "center", "band"),
    # Abschnitte der Startseite trennen
    "sections": ("none", "line", "alternate"),
    # Fuß
    "footer": ("dark", "light", "color"),
    "footer_align": ("left", "center", "right"),
    # Ralf 14.11.2026: Überschrift der Unterseiten, Schrift der Überschriften, Menüschrift,
    # sanftes Einblenden, gestreifte Tabellen, Datum neben dem Datumsfeld
    "page_title": ("plain", "band", "image"),
    "heading_font": ("text", "modern", "festive"),
    "nav_case": ("normal", "upper"),
    "nav_size": ("normal", "large"),
    "motion": ("off", "subtle"),
    "stripes": bool,
    "date_text": ("weekday", "short", "long"),
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


# Was jedes Design ohne verstellten Regler zeigt (Ralf 14.11.2026): HUBIplan markiert die
# Stufe als „Design“. Fehlt ein Regler, liegt das Design zwischen den Stufen (z. B. Ecken mit
# 10 px) oder hat eine eigene Form; dann bleibt die Markierung weg. Abgelesen aus seite.css
# und design-<name>.css in hubiplan-website; Designpakete haben keine Vorgaben.
_BASE_DEFAULTS: dict[str, str | bool] = {
    "font": "system",
    "size": "normal",
    "leading": "normal",
    "headings": "plain",
    "heading_align": "left",
    "script_greeting": False,
    "width": "normal",
    "background": "light",
    "spacing": "normal",
    "dark": "off",
    "contrast": False,
    "to_top": False,
    "cards": "border",
    "images": "cards",
    "tile_ratio": "wide",
    "image_frame": False,
    "buttons": "filled",
    "date": "tile",
    "header_bg": "color",
    "logo": True,
    "logo_pos": "left",
    "name": True,
    "header_height": "normal",
    "line": "none",
    "nav": "text",
    "nav_active": "underline",
    "sticky": False,
    "nav_mobile": "toggle",
    "nav_start": True,
    "search": "nav",
    "hero": "normal",
    "hero_name": False,
    "carousel": "normal",
    "hero_shade": "none",
    "hero_tint": "dark",
    "hero_focus": "center",
    "hero_text": "top",
    "sections": "none",
    "footer": "dark",
    "page_title": "plain",
    "heading_font": "text",
    "nav_case": "normal",
    "nav_size": "normal",
    "motion": "off",
    "stripes": False,
    "date_text": "weekday",
}
_DESIGN_DEFAULTS: dict[str, dict[str, str | bool | None]] = {
    "classic": {
        "header_bg": "white",
        "line": None,
        "nav": "buttons",
        "nav_active": "filled",
        "headings": "color",
        "cards": "shadow",
        "footer": "color",
    },
    "festive": {
        "heading_font": "festive",
        "logo_pos": "center",
        "header_height": "high",
        "heading_align": "center",
        "headings": None,
        "corners": "slight",
        "footer_align": "center",
        "line": None,
    },
    "newspaper": {
        "header_bg": "white",
        "heading_font": "festive",
        "headings": "line",
        "nav": "bar",
        "nav_active": "filled",
        "line": None,
    },
    "sidebar": {"logo_pos": "center", "nav": None, "header_height": None},
    "stage": {
        "sticky": True,
        "hero_name": True,
        "hero_text": "band",
        "hero": None,
        "sections": "alternate",
        "line": None,
    },
}


def defaults(design: str) -> dict[str, str | bool]:
    """Stufe, die ein Standarddesign ohne verstellten Regler zeigt (ohne Zwischenstufen)."""
    if design not in _DESIGN_DEFAULTS:
        return {}
    merged = {**_BASE_DEFAULTS, **_DESIGN_DEFAULTS[design]}
    return {k: v for k, v in merged.items() if v is not None and k in OPTIONS}


# Voreinstellungen mit einem Klick (Ralf 14.11.2026): setzen mehrere Regler auf einmal, alles
# bleibt danach einzeln änderbar. Namen stehen in der Oberfläche (StyleTuning.tsx).
PRESETS: dict[str, dict[str, str | bool]] = {
    "calm": {
        "font": "system",
        "headings": "plain",
        "spacing": "generous",
        "corners": "slight",
        "cards": "border",
        "line": "none",
        "nav": "text",
        "hero_shade": "none",
        "sections": "line",
        "page_title": "plain",
        "motion": "off",
    },
    "festive": {
        "font": "festive",
        "heading_font": "festive",
        "headings": "color",
        "heading_align": "center",
        "script_greeting": True,
        "line": "strong",
        "nav_case": "upper",
        "hero_shade": "light",
        "hero_tint": "primary",
        "hero_text": "center",
        "page_title": "image",
        "sections": "alternate",
    },
    "modern": {
        "font": "modern",
        "heading_font": "modern",
        "corners": "round",
        "cards": "shadow",
        "buttons": "filled",
        "nav": "buttons",
        "nav_active": "filled",
        "hero_shade": "light",
        "hero_tint": "dark",
        "hero_text": "band",
        "page_title": "band",
        "motion": "subtle",
    },
    "readable": {
        "size": "large",
        "leading": "airy",
        "contrast": True,
        "cards": "border",
        "buttons": "filled",
        "nav_size": "large",
        "stripes": True,
        "date_text": "long",
        "motion": "off",
        "to_top": True,
    },
}


def catalog() -> dict:
    """Für die Oberfläche: Stufen je Regler, Sperren und Vorgaben je Design, Voreinstellungen."""
    from .designs import DESIGNS

    return {
        "options": {k: "switch" if v is bool else list(v) for k, v in OPTIONS.items()},
        "locks": {
            design: {k: None if v is None else list(v) for k, v in locks.items()}
            for design, locks in LOCKS.items()
        },
        "defaults": {design: defaults(design) for design in DESIGNS},
        "presets": PRESETS,
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
