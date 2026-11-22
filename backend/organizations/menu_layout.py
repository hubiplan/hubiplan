"""Anordnung des Menüs je Einheit (Konzept konzepte/menue-frei-anordnen.md).

Die Einheit legt fest, welche Hauptmenüpunkte (Bereiche) es gibt und in welchem Bereich ein
Menüpunkt steht. Gespeichert werden nur Abweichungen vom Standard::

    {"v": 1,
     "areas": [{"id": "start"}, {"id": "mitglieder"}, {"id": "webseite"},
               {"id": "b1", "label": "Schießsport", "label_en": "Shooting", "icon": "wettbewerbe"}],
     "items": {"geschaeftspartner": "verein"}}

Regeln für den Ort eines Menüpunkts: ausdrücklich in ``items`` genannt; sonst ein Bereich mit
derselben Kennung wie der Menüpunkt (Menüpunkt als eigener Hauptmenüpunkt); sonst sein
Standardbereich; gibt es den nicht mehr, der erste Bereich nach Start.

Die Anordnung bestimmt nur den Ort. Was jemand sieht, entscheiden weiter Module und Rechte.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path

from rest_framework.exceptions import ValidationError

VERSION = 1
MAX_AREAS = 12
MIN_AREAS = 2
MAX_LABEL = 24
HISTORY = 5
# Menüpunkte, die nicht verschoben werden: Startseite und Plattform (nur Betreiber)
FIXED = {"start": "start"}
PINNED = {"plattform"}
CUSTOM_ID = re.compile(r"^b([1-9][0-9]?)$")


@cache
def standard() -> dict:
    data = json.loads((Path(__file__).with_name("menu_standard.json")).read_text("utf-8"))
    data.pop("_hinweis", None)
    data.pop("labels", None)
    return data


@cache
def item_labels() -> dict[str, list[str]]:
    """Namen der Menüpunkte (deutsch, englisch) für Bereiche aus einem Menüpunkt."""
    data = json.loads((Path(__file__).with_name("menu_standard.json")).read_text("utf-8"))
    return data.get("labels", {})


def standard_area_ids() -> list[str]:
    return [a["id"] for a in standard()["areas"]]


def item_ids() -> list[str]:
    return list(standard()["items"])


def icon_keys() -> set[str]:
    """Zeichen eigener Bereiche: die eines Standardbereichs oder eines Menüpunkts."""
    return set(standard_area_ids()) | set(item_ids())


def _label(value, field: str, required: bool) -> str:
    if value is None or value == "":
        if required:
            raise ValidationError({field: "Bitte einen Namen angeben."})
        return ""
    if not isinstance(value, str):
        raise ValidationError({field: "Ungültiger Name."})
    value = " ".join(value.split())
    if len(value) > MAX_LABEL:
        raise ValidationError({field: f"Höchstens {MAX_LABEL} Zeichen."})
    return value


def clean(layout) -> dict | None:
    """Prüft eine Anordnung und gibt sie bereinigt zurück; None heißt Standard."""
    if layout is None:
        return None
    if not isinstance(layout, dict):
        raise ValidationError({"layout": "Ungültige Anordnung."})
    raw_areas = layout.get("areas")
    if not isinstance(raw_areas, list):
        raise ValidationError({"areas": "Ungültige Anordnung."})
    if not MIN_AREAS <= len(raw_areas) <= MAX_AREAS:
        raise ValidationError({"areas": f"Es braucht {MIN_AREAS} bis {MAX_AREAS} Hauptmenüpunkte."})
    std = set(standard_area_ids())
    items = set(item_ids())
    areas: list[dict] = []
    seen: set[str] = set()
    for raw in raw_areas:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
            raise ValidationError({"areas": "Ungültiger Hauptmenüpunkt."})
        area_id = raw["id"]
        custom = CUSTOM_ID.match(area_id) is not None
        if area_id in seen:
            raise ValidationError({"areas": "Ein Hauptmenüpunkt steht doppelt."})
        if not (area_id in std or area_id in items or custom) or area_id in PINNED:
            raise ValidationError({"areas": "Unbekannter Hauptmenüpunkt."})
        seen.add(area_id)
        entry: dict = {"id": area_id}
        label = _label(raw.get("label"), "label", required=custom)
        if label:
            entry["label"] = label
            label_en = _label(raw.get("label_en"), "label_en", required=False)
            if label_en:
                entry["label_en"] = label_en
        icon = raw.get("icon")
        if icon not in (None, ""):
            if icon not in icon_keys():
                raise ValidationError({"icon": "Unbekanntes Zeichen."})
            entry["icon"] = icon
        areas.append(entry)
    if areas[0]["id"] != "start":
        raise ValidationError({"areas": "Start bleibt der erste Hauptmenüpunkt."})
    raw_items = layout.get("items") or {}
    if not isinstance(raw_items, dict):
        raise ValidationError({"items": "Ungültige Zuordnung."})
    placed: dict[str, str] = {}
    for item, area_id in raw_items.items():
        # Unbekannte Menüpunkte (ältere oder neuere Fassung) werden übergangen
        if item not in items or item in PINNED:
            continue
        if area_id not in seen:
            raise ValidationError({"items": "Ein Menüpunkt verweist auf einen fehlenden Bereich."})
        if item in FIXED and area_id != FIXED[item]:
            raise ValidationError({"items": "Die Startseite bleibt unter Start."})
        placed[item] = area_id
    result = {"v": VERSION, "areas": areas, "items": placed}
    # Nichts verändert: wie Standard speichern
    return None if _is_standard(result) else result


def _is_standard(layout: dict) -> bool:
    return (
        [a["id"] for a in layout["areas"]] == standard_area_ids()
        and all(set(a) == {"id"} for a in layout["areas"])
        and all(area_of(layout, i) == standard()["items"][i] for i in item_ids())
    )


def area_of(layout: dict | None, item: str) -> str:
    """Bereich eines Menüpunkts nach den Regeln oben."""
    default = standard()["items"].get(item, "verein")
    if not layout:
        return default
    ids = [a["id"] for a in layout["areas"]]
    if item in PINNED:
        return default if default in ids else ids[-1]
    chosen = (layout.get("items") or {}).get(item)
    if chosen in ids:
        return chosen
    if item in ids:
        return item
    if default in ids:
        return default
    return ids[1] if len(ids) > 1 else ids[0]


def owner(org):
    """Die Einheit, deren Anordnung gilt: Untereinheiten übernehmen die ihres Vereins."""
    if getattr(org, "type", None) == "unit" and getattr(org, "organization", None) is not None:
        return org.organization
    return org


def effective(org) -> dict | None:
    return owner(org).menu_layout if org is not None else None


def save(org, layout, user) -> dict | None:
    """Speichert eine geprüfte Anordnung und merkt sich die vorige für Rückgängig."""
    cleaned = clean(layout)
    if cleaned == org.menu_layout:
        return cleaned
    history = list(org.menu_layout_history or [])
    history.append({"layout": org.menu_layout})
    org.menu_layout_history = history[-HISTORY:]
    org.menu_layout = cleaned
    org.save(update_fields=["menu_layout", "menu_layout_history"])
    return cleaned


def undo(org) -> dict | None:
    history = list(org.menu_layout_history or [])
    if not history:
        raise ValidationError({"detail": "Es gibt keine frühere Anordnung."})
    previous = history.pop().get("layout")
    # Eine früher gespeicherte Anordnung kann Menüpunkte nennen, die es nicht mehr gibt
    try:
        previous = clean(previous)
    except ValidationError:
        previous = None
    org.menu_layout = previous
    org.menu_layout_history = history
    org.save(update_fields=["menu_layout", "menu_layout_history"])
    return previous


def groups(org, lang: str = "de") -> list[dict]:
    """Bereiche der Einheit mit ihren Menüpunkten, für die Apps (``menu_groups``)."""
    layout = effective(org)
    std = {a["id"]: a for a in standard()["areas"]}
    areas = layout["areas"] if layout else [{"id": a} for a in standard_area_ids()]
    result = []
    for area in areas:
        base = std.get(area["id"], {})
        if lang == "en":
            label = area.get("label_en") or area.get("label") or base.get("label_en")
        else:
            label = area.get("label") or base.get("label")
        if not label and area["id"] in item_labels():
            label = item_labels()[area["id"]][1 if lang == "en" else 0]
        members = [i for i in item_ids() if area_of(layout, i) == area["id"]]
        result.append({"id": area["id"], "label": label or area["id"], "items": members})
    return result
