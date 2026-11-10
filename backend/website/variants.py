"""Darstellung der festen Bereiche (Konzept webseite-baukasten G5, Ralf 10.11.2026).

Je Bereich zwei bis drei feste Varianten; die erste ist der bisherige Stand. Gespeichert
werden nur abweichende Varianten in ``Website.layouts``; die Webseite bekommt alle.
Dazu je Bereich ein optionaler Einleitungstext (WebsiteText der Art „intro“).
"""

from __future__ import annotations

from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

# Bereich → Varianten (erste = Standard, wie bisher)
VARIANTS: dict[str, tuple[str, ...]] = {
    "board": ("cards", "list"),
    "events": ("list", "calendar"),
    "units": ("large", "small", "list"),
    "gallery": ("tiles", "masonry"),
}

VARIANT_LABELS = {
    "board": {"cards": _("Karten mit Foto"), "list": _("Kompakte Liste")},
    "events": {"list": _("Liste nach Monaten"), "calendar": _("Monatskalender")},
    "units": {
        "large": _("Große Kacheln mit Wappen"),
        "small": _("Kleine Kacheln"),
        "list": _("Liste"),
    },
    "gallery": {"tiles": _("Kacheln"), "masonry": _("Mauerwerk")},
}

# Bereiche mit Einleitungstext (Art „intro“, Adresse = Schlüssel des Bereichs)
INTRO_AREAS = tuple(VARIANTS)


def normalize(value) -> dict[str, str]:
    """Nur bekannte Bereiche mit gültiger, vom Standard abweichender Variante."""
    if not isinstance(value, dict):
        return {}
    return {
        area: value[area] for area, choices in VARIANTS.items() if value.get(area) in choices[1:]
    }


def validate(value) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError(gettext("Darstellung bitte je Bereich angeben."))
    for area, choice in value.items():
        if area not in VARIANTS:
            raise ValueError(gettext("Unbekannter Bereich: {x0}").format(x0=area))
        if choice not in VARIANTS[area]:
            raise ValueError(gettext("Unbekannte Darstellung: {x0}").format(x0=choice))
    return normalize(value)


def public(value) -> dict[str, str]:
    """Alle Bereiche mit ihrer Variante, für die Webseite."""
    chosen = normalize(value)
    return {area: chosen.get(area, choices[0]) for area, choices in VARIANTS.items()}


def catalog() -> list[dict]:
    """Für die Oberfläche: Bereich, Varianten mit Bezeichnung (Skizzen zeichnet das Frontend)."""
    return [
        {
            "area": area,
            "variants": [{"key": key, "label": str(VARIANT_LABELS[area][key])} for key in choices],
        }
        for area, choices in VARIANTS.items()
    ]
