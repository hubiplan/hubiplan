"""Standarddesigns der Vereinswebseite und Zuordnung der Einheitsfarben zu Rollen.

Ein Design legt Aufbau (Kopf, Menü, Fuß, Startseite) fest; die Webseite zeichnet es.
HUBIplan bestimmt nur, welche Farbe aus der Palette der Einheit welche Rolle bekommt
(Konzept konzepte/webseiten-designs.md, Ralf 2026-10-31).
"""

from __future__ import annotations

from organizations.theme import DARK_TEXT, LIGHT_TEXT, text_color_on

DEFAULT_DESIGN = "classic"

# Rollen, in denen ein Design Farben einsetzt
ROLES = {
    "header": "Kopf",
    "nav": "Menü (Leiste oder Markierung)",
    "line": "Zierlinien",
    "footer": "Fuß",
    "band": "Farbband",
    "band2": "zweites Farbband",
    "date": "Datumsfeld bei Terminen",
}

# Feste Werte neben den Palettenplätzen
NEUTRAL = {"dark": DARK_TEXT, "light": LIGHT_TEXT}

# Je Design: Name, Beschreibung und Vorgaben je Rolle. Eine Vorgabe ist eine Liste
# von Palettenplätzen (0 = Hauptfarbe, 1 = Zweitfarbe, 2 … = weitere Farben) oder ein
# fester Wert; der erste vorhandene Platz gilt.
DESIGNS: dict[str, dict] = {
    "classic": {
        "label": "Klassisch",
        "hint": (
            "Heller Kopf mit farbiger Linie, Menü als Knöpfe in der Vereinsfarbe, "
            "Karten mit Schatten."
        ),
        "roles": {
            "header": [0],
            "nav": [1],
            "line": [1],
            "footer": [0],
            "date": [0],
        },
    },
    "festive": {
        "label": "Festlich",
        "hint": "Wappen groß und mittig, Menüleiste mit Zierlinien, Überschriften mit Serifen.",
        "roles": {
            "header": [0],
            "nav": [1],
            "line": [1],
            "footer": [0],
            "date": [2, 0],
        },
    },
    "sidebar": {
        "label": "Seitenleiste",
        "hint": "Menü senkrecht in einer Leiste links, auf dem Handy schmaler Kopf.",
        "roles": {
            "header": [0],
            "nav": [1],
            "line": [1],
            "footer": "light",
            "date": [0],
        },
    },
    "stage": {
        "label": "Bühne",
        "hint": "Heller Kopf, großes Titelbild mit dem Namen, Startseite in farbigen Bändern.",
        "roles": {
            "header": "light",
            "nav": [0],
            "line": [1],
            "footer": [0],
            "band": [0],
            "band2": [2, 0],
            "date": [1],
        },
    },
    "newspaper": {
        "label": "Zeitung",
        "hint": "Kontaktleiste oben, Menü als Reiter, Startseite in zwei Spalten.",
        "roles": {
            "header": [0],
            "nav": [1],
            "line": [2, 0],
            "footer": "dark",
            "date": [0],
        },
    },
}


def _pick(spec, palette: list[dict]) -> str:
    if isinstance(spec, str):
        return NEUTRAL.get(spec, NEUTRAL["dark"])
    for index in spec:
        if 0 <= index < len(palette):
            return palette[index]["color"]
    return palette[0]["color"]


def valid_choice(value) -> bool:
    """Gespeicherte Wahl je Rolle: Palettenplatz 0–5 oder „dark“/„light“."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return 0 <= value <= 5
    return value in NEUTRAL


def _role_specs(extra: dict | None = None) -> dict[str, dict]:
    """Vorgaben je Rolle für alle bekannten Designs: Standarddesigns und Pakete."""
    specs = {key: d["roles"] for key, d in DESIGNS.items()}
    specs.update(extra or {})
    return specs


def normalize_color_roles(value, extra: dict | None = None) -> dict:
    """{design: {rolle: wahl}} → nur bekannte Designs, Rollen und Werte.

    ``extra``: Rollen eingespielter Designpakete ({schlüssel: {rolle: vorgabe}})."""
    result: dict[str, dict] = {}
    if not isinstance(value, dict):
        return result
    specs = _role_specs(extra)
    for key, roles in value.items():
        if key not in specs or not isinstance(roles, dict):
            continue
        used = specs[key]
        clean = {r: v for r, v in roles.items() if r in used and valid_choice(v)}
        if clean:
            result[key] = clean
    return result


def resolve(
    design: str, palette: list[dict], color_roles: dict | None = None, extra: dict | None = None
) -> dict:
    """Farben je Rolle für ein Design: {rolle: {color, on_color}}."""
    specs = _role_specs(extra)
    spec = specs.get(design, DESIGNS[DEFAULT_DESIGN]["roles"])
    chosen = normalize_color_roles(color_roles or {}, extra).get(design, {})
    result = {}
    for role, default in spec.items():
        choice = chosen.get(role)
        if isinstance(choice, int):
            color = _pick([choice], palette) if choice < len(palette) else _pick(default, palette)
        elif isinstance(choice, str):
            color = NEUTRAL[choice]
        else:
            color = _pick(default, palette)
        result[role] = {"color": color, "on_color": text_color_on(color)}
    return result


def package_roles(packages) -> dict:
    """{schlüssel: rollen} der übergebenen Designpakete."""
    return {p.key: p.roles for p in packages}


def _role_list(roles: dict) -> list[dict]:
    return [
        {
            "key": role,
            "label": ROLES[role],
            "default": spec if isinstance(spec, str) else spec[0],
        }
        for role, spec in roles.items()
        if role in ROLES
    ]


# Skizzen in der Oberfläche: je Standarddesign eine, dazu der Aufbau früherer Fassungen für
# Designpakete, die aus ihnen exportiert wurden („classic-1“ = Klassisch bis 2026-11).
SKETCHES = (*DESIGNS, "classic-1")


def catalog(packages=(), language: str = "de") -> list[dict]:
    """Für die Oberfläche: Standarddesigns und freigegebene Designpakete mit Rollen."""
    result = [
        {
            "key": key,
            "label": d["label"],
            "hint": d["hint"],
            "package": False,
            "sketch": key,
            "roles": _role_list(d["roles"]),
        }
        for key, d in DESIGNS.items()
    ]
    for p in packages:
        result.append(
            {
                "key": p.key,
                "label": p.label_for(language),
                "hint": p.hint_for(language),
                "package": True,
                "sketch": p.sketch_like if p.sketch_like in SKETCHES else DEFAULT_DESIGN,
                "roles": _role_list(p.roles),
            }
        )
    return result


def export_catalog() -> dict:
    """Steckbriefe der Standarddesigns (Deutsch und Englisch) für den Export als Paket."""
    from django.utils import translation

    result = {}
    for key, d in DESIGNS.items():
        with translation.override("en"):
            label_en, hint_en = translation.gettext(d["label"]), translation.gettext(d["hint"])
        result[key] = {
            "label": d["label"],
            "label_en": label_en,
            "hint": d["hint"],
            "hint_en": hint_en,
            "roles": d["roles"],
        }
    return result
