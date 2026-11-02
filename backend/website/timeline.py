"""Zeitleiste der Chronik: kurze Einträge mit Jahr, Überschrift, Text und Bildern.

Neben Ereignissen gibt es Kapitel (``kind`` = ``chapter``, Ralf 02.11.), z. B.
„Gründerjahre 1920–1938“: eine Zwischenüberschrift, unter der die Webseite alle
Ereignisse ab ihrem Jahr bis zum nächsten Kapitel zeigt. Kapitel haben kein Bild.

Ein Ereignis hat bis zu sechs Bilder (``images``, Ralf 02.11.) und eine Bildposition
(``image_position``: auto = abwechselnd, left, right, below = groß unter dem Text).
Ältere Einträge hatten ein einzelnes ``image``; :func:`entry_images` liest beide Formen.

Die Zeitleiste gehört zur Textseite „Chronik“ (Adresse ``geschichte``) und wird mit ihr
als Entwurf gespeichert und veröffentlicht. Die Webseite zeigt sie nach Jahren sortiert.
"""

from __future__ import annotations

import re

from django.utils.translation import gettext
from rest_framework.exceptions import ValidationError

from exchange.reading import ReadError, read_table

from .content_models import (
    MAX_TIMELINE,
    MAX_TIMELINE_IMAGES,
    MAX_TIMELINE_TEXT,
    MAX_TIMELINE_TITLE,
    WebsiteImage,
)

MIN_YEAR = 1000
MAX_YEAR = 2999
EVENT, CHAPTER = "event", "chapter"
KINDS = (EVENT, CHAPTER)
# Bildposition je Ereignis (Ralf 02.11.): automatisch = abwechselnd links/rechts
POSITIONS = ("auto", "left", "right", "below")
CHAPTER_WORDS = ("kapitel", "abschnitt", "chapter", "section")
COLUMNS = {
    "kind": ("art", "typ", "kind", "type"),
    "year": ("jahr", "von", "datum", "year", "from"),
    "until": ("bis", "endjahr", "bis jahr", "until", "to"),
    "title": ("überschrift", "ueberschrift", "titel", "ereignis", "title", "event"),
    "text": ("text", "beschreibung", "kurztext", "description"),
}


def entry_images(entry) -> list[int]:
    """Bildnummern eines Eintrags, auch aus der alten Form mit einem ``image``."""
    if not isinstance(entry, dict):
        return []
    images = entry.get("images")
    if not isinstance(images, list):
        images = [entry.get("image")]
    ids = [pk for pk in images if isinstance(pk, int) and not isinstance(pk, bool)]
    return list(dict.fromkeys(ids))


def with_images(entry: dict, images: list[int]) -> dict:
    """Eintrag in der neuen Form mit ``images`` (ohne das alte ``image``)."""
    result = {k: v for k, v in entry.items() if k != "image"}
    result["images"] = images
    return result


def _year(value) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if hasattr(value, "year"):
        return value.year
    match = re.fullmatch(r"\s*(\d{3,4})\s*", str(value))
    return int(match.group(1)) if match else None


def entry_errors(entry: dict) -> list[str]:
    """Fehler eines Eintrags (bereits als Zahl/Text gelesen)."""
    errors = []
    year, until = entry.get("year"), entry.get("until")
    if year is None or not MIN_YEAR <= year <= MAX_YEAR:
        errors.append(gettext("Bitte ein Jahr zwischen 1000 und 2999 angeben."))
    if until is not None:
        if not MIN_YEAR <= until <= MAX_YEAR:
            errors.append(gettext("Das Jahr „bis“ ist ungültig."))
        elif year is not None and until < year:
            errors.append(gettext("Das Jahr „bis“ liegt vor dem Jahr."))
    if not entry.get("title"):
        errors.append(gettext("Bitte eine Überschrift angeben."))
    elif len(entry["title"]) > MAX_TIMELINE_TITLE:
        errors.append(
            gettext("Die Überschrift darf höchstens {n} Zeichen haben.").format(
                n=MAX_TIMELINE_TITLE
            )
        )
    if len(entry.get("text") or "") > MAX_TIMELINE_TEXT:
        errors.append(
            gettext("Der Text darf höchstens {n} Zeichen haben.").format(n=MAX_TIMELINE_TEXT)
        )
    return errors


def clean_timeline(value, website) -> list[dict]:
    """Zeitleiste aus dem Browser prüfen und in feste Form bringen."""
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValidationError(gettext("Ungültige Zeitleiste."))
    if len(value) > MAX_TIMELINE:
        raise ValidationError(
            gettext("Höchstens {n} Einträge in der Zeitleiste.").format(n=MAX_TIMELINE)
        )
    result = []
    for index, raw in enumerate(value, start=1):
        if not isinstance(raw, dict):
            raise ValidationError(gettext("Ungültige Zeitleiste."))
        raw_images = raw.get("images")
        if raw_images is None:
            raw_images = [] if raw.get("image") is None else [raw.get("image")]
        if not isinstance(raw_images, list) or any(
            not isinstance(pk, int) or isinstance(pk, bool) for pk in raw_images
        ):
            raise ValidationError(gettext("Ungültige Zeitleiste."))
        images = list(dict.fromkeys(raw_images))
        kind = raw.get("kind") or EVENT
        if kind not in KINDS:
            raise ValidationError(gettext("Ungültige Zeitleiste."))
        position = raw.get("image_position") or "auto"
        if position not in POSITIONS:
            raise ValidationError(gettext("Ungültige Zeitleiste."))
        if kind == CHAPTER:
            images, position = [], "auto"
        if len(images) > MAX_TIMELINE_IMAGES:
            raise ValidationError(
                gettext("Eintrag {n}: höchstens {max} Bilder.").format(
                    n=index, max=MAX_TIMELINE_IMAGES
                )
            )
        entry = {
            "kind": kind,
            "year": _year(raw.get("year")),
            "until": _year(raw.get("until")),
            "title": str(raw.get("title") or "").strip(),
            "text": str(raw.get("text") or "").strip().replace("\r\n", "\n"),
            "images": images,
            "image_position": position,
        }
        if entry["until"] == entry["year"]:
            entry["until"] = None
        errors = entry_errors(entry)
        if errors:
            raise ValidationError(
                gettext("Eintrag {n}: {error}").format(n=index, error=" ".join(errors))
            )
        result.append(entry)
    images = {pk for e in result for pk in e["images"]}
    known = set(
        WebsiteImage.objects.filter(website=website, pk__in=images).values_list("pk", flat=True)
    )
    if images - known:
        raise ValidationError(gettext("Unbekanntes Bild in der Zeitleiste."))
    return result


def sorted_timeline(timeline) -> list[dict]:
    """Nach Jahr sortiert, ein Kapitel vor den Ereignissen seines Jahres; sonst bleiben
    gleiche Jahre in ihrer Reihenfolge."""
    entries = [e for e in timeline or [] if isinstance(e, dict) and e.get("year")]
    return sorted(entries, key=lambda e: (e["year"], e.get("kind") != CHAPTER))


def _map_columns(headers: list[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for index, header in enumerate(headers):
        h = str(header).strip().lower()
        for target, names in COLUMNS.items():
            if target not in result and h in names:
                result[target] = index
    return result


def read_import(path, file_name: str) -> dict:
    """Einträge aus Excel oder CSV (Spalten Jahr, Überschrift, optional bis, Text und Art:
    „Kapitel“ für eine Zwischenüberschrift, sonst Ereignis).

    Liefert {"entries": [...], "errors": [{"line", "message"}], "error": ""}. Gespeichert
    wird nichts: Die Einträge kommen in den Entwurf und lassen sich dort noch ändern.
    """
    try:
        headers, rows = read_table(path, file_name)
    except ReadError as exc:
        return {"error": str(exc), "entries": [], "errors": []}
    columns = _map_columns(headers)
    missing = [
        label
        for key, label in (("year", gettext("Jahr")), ("title", gettext("Überschrift")))
        if key not in columns
    ]
    if missing:
        return {
            "error": gettext("Es fehlen die Spalten: {missing}. Gefunden: {found}.").format(
                missing=", ".join(missing), found=", ".join(headers)
            ),
            "entries": [],
            "errors": [],
        }
    if len(rows) > MAX_TIMELINE:
        return {
            "error": gettext("Höchstens {n} Einträge in der Zeitleiste.").format(n=MAX_TIMELINE),
            "entries": [],
            "errors": [],
        }

    def cell(row, key):
        index = columns.get(key)
        value = row[index] if index is not None else None
        return "" if value is None else value

    entries, errors = [], []
    for line, row in enumerate(rows, start=2):
        year_raw, until_raw = cell(row, "year"), cell(row, "until")
        kind_raw = str(cell(row, "kind")).strip().lower()
        entry = {
            "kind": CHAPTER if kind_raw in CHAPTER_WORDS else EVENT,
            "year": _year(year_raw),
            "until": _year(until_raw),
            "title": str(cell(row, "title")).strip(),
            "text": str(cell(row, "text")).strip().replace("\r\n", "\n"),
            "images": [],
            "image_position": "auto",
        }
        problems = entry_errors(entry)
        if str(until_raw).strip() and entry["until"] is None:
            problems.append(gettext("Das Jahr „bis“ ist ungültig."))
        if entry["until"] == entry["year"]:
            entry["until"] = None
        if problems:
            errors.append({"line": line, "message": " ".join(problems)})
        else:
            entries.append(entry)
    return {"error": "", "entries": entries, "errors": errors}
