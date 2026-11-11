"""Standarddesigns der Vereinswebseite und Zuordnung der Einheitsfarben zu Rollen.

Ein Design legt Aufbau (Kopf, Menü, Fuß, Startseite) fest; die Webseite zeichnet es.
HUBIplan bestimmt nur, welche Farbe aus der Palette der Einheit welche Rolle bekommt
(Konzept konzepte/webseiten-designs.md, Ralf 2026-10-31).
"""

from __future__ import annotations

from django.utils.translation import gettext, gettext_noop

from organizations.theme import DARK_TEXT, LIGHT_TEXT, text_color_on

DEFAULT_DESIGN = "classic"

# Rollen, in denen ein Design Farben einsetzt
ROLES = {
    "header": gettext_noop("Kopf"),
    "nav": gettext_noop("Menü (Leiste oder Markierung)"),
    "line": gettext_noop("Zierlinien"),
    "footer": gettext_noop("Fuß"),
    "band": gettext_noop("Farbband"),
    "band2": gettext_noop("zweites Farbband"),
    "date": gettext_noop("Datumsfeld bei Terminen"),
}

# Rollen, die jedes Design kennt (Ralf 10.11.2026): ohne Wahl bleibt das Design, wie es ist
COMMON_ROLES = {
    "text": gettext_noop("Fließtext"),
    "muted": gettext_noop("Sekundärtext"),
    "surface": gettext_noop("Flächen (Karten, Tabellenzeilen)"),
    "background": gettext_noop("Seitenhintergrund"),
}

# Rollen, die statt einer Farbe auch einen Verlauf nehmen können (flächig oder Linien)
GRADIENT_ROLES = ("header", "footer", "band", "band2", "line")

# Feste Werte neben den Palettenplätzen
NEUTRAL = {"dark": DARK_TEXT, "light": LIGHT_TEXT}
# Verläufe aus Einstellungen › Erscheinungsbild: „g0“ = erster, „g1“ = zweiter
GRADIENT_CHOICES = ("g0", "g1")

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


def valid_choice(value, role: str | None = None) -> bool:
    """Gespeicherte Wahl je Rolle: Palettenplatz 0–5, „dark“/„light“ oder ein Verlauf."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return 0 <= value <= 5
    if value in GRADIENT_CHOICES:
        return role in GRADIENT_ROLES
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
        clean = {
            r: v
            for r, v in roles.items()
            if (r in used or r in COMMON_ROLES) and valid_choice(v, r)
        }
        if clean:
            result[key] = clean
    return result


def _gradient(choice, gradients: list[dict] | None) -> dict | None:
    index = GRADIENT_CHOICES.index(choice)
    return gradients[index] if gradients and index < len(gradients) else None


def resolve(
    design: str,
    palette: list[dict],
    color_roles: dict | None = None,
    extra: dict | None = None,
    gradients: list[dict] | None = None,
) -> dict:
    """Farben je Rolle für ein Design: {rolle: {color, on_color[, gradient]}}.

    ``gradients`` aus ``effective_theme``; ein Verlauf liefert seine erste Farbe als
    ``color`` (für ältere Webseiten) und ``gradient`` = {from, to, direction}. Rollen aus
    COMMON_ROLES erscheinen nur, wenn jemand sie gewählt hat."""
    specs = _role_specs(extra)
    spec = specs.get(design, DESIGNS[DEFAULT_DESIGN]["roles"])
    chosen = normalize_color_roles(color_roles or {}, extra).get(design, {})
    result = {}
    roles = {**spec, **{r: None for r in COMMON_ROLES if r in chosen}}
    for role, default in roles.items():
        choice = chosen.get(role)
        entry = None
        if isinstance(choice, int):
            if choice < len(palette):
                color = palette[choice]["color"]
            elif default is not None:
                color = _pick(default, palette)
            else:
                continue
        elif choice in GRADIENT_CHOICES:
            g = _gradient(choice, gradients)
            if g is not None:
                start, end = g["colors"]
                entry = {
                    "color": start,
                    "on_color": g["on_color"],
                    "gradient": {"from": start, "to": end, "direction": g["direction"]},
                }
            color = _pick(default, palette)
        elif isinstance(choice, str):
            color = NEUTRAL[choice]
        else:
            color = _pick(default, palette)
        result[role] = entry or {"color": color, "on_color": text_color_on(color)}
    return result


def package_roles(packages) -> dict:
    """{schlüssel: rollen} der übergebenen Designpakete."""
    return {p.key: p.roles for p in packages}


def _role_list(roles: dict) -> list[dict]:
    result = [
        {
            "key": role,
            "label": gettext(ROLES[role]),
            "default": spec if isinstance(spec, str) else spec[0],
            "gradient": role in GRADIENT_ROLES,
        }
        for role, spec in roles.items()
        if role in ROLES
    ]
    # Text, Flächen und Hintergrund: in jedem Design, Vorgabe ist das Design selbst
    result += [
        {"key": role, "label": gettext(label), "default": None, "gradient": False, "common": True}
        for role, label in COMMON_ROLES.items()
    ]
    return result


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
