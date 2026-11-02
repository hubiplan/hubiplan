"""Zeitleiste der Chronik: kurze Einträge mit Jahr, Überschrift, Text und Bild.

Neben Ereignissen gibt es Kapitel (``kind`` = ``chapter``, Ralf 02.11.), z. B.
„Gründerjahre 1920–1938“: eine Zwischenüberschrift, unter der die Webseite alle
Ereignisse ab ihrem Jahr bis zum nächsten Kapitel zeigt. Kapitel haben kein Bild.

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
    MAX_TIMELINE_TEXT,
    MAX_TIMELINE_TITLE,
    WebsiteImage,
)

MIN_YEAR = 1000
MAX_YEAR = 2999
EVENT, CHAPTER = "event", "chapter"
KINDS = (EVENT, CHAPTER)
CHAPTER_WORDS = ("kapitel", "abschnitt", "chapter", "section")
COLUMNS = {
    "kind": ("art", "typ", "kind", "type"),
    "year": ("jahr", "von", "datum", "year", "from"),
    "until": ("bis", "endjahr", "bis jahr", "until", "to"),
    "title": ("überschrift", "ueberschrift", "titel", "ereignis", "title", "event"),
    "text": ("text", "beschreibung", "kurztext", "description"),
}


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
        image = raw.get("image")
        if image is not None and (not isinstance(image, int) or isinstance(image, bool)):
            raise ValidationError(gettext("Ungültige Zeitleiste."))
        kind = raw.get("kind") or EVENT
        if kind not in KINDS:
            raise ValidationError(gettext("Ungültige Zeitleiste."))
        if kind == CHAPTER:
            image = None
        entry = {
            "kind": kind,
            "year": _year(raw.get("year")),
            "until": _year(raw.get("until")),
            "title": str(raw.get("title") or "").strip(),
            "text": str(raw.get("text") or "").strip().replace("\r\n", "\n"),
            "image": image,
        }
        if entry["until"] == entry["year"]:
            entry["until"] = None
        errors = entry_errors(entry)
        if errors:
            raise ValidationError(
                gettext("Eintrag {n}: {error}").format(n=index, error=" ".join(errors))
            )
        result.append(entry)
    images = {e["image"] for e in result if e["image"] is not None}
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
            "image": None,
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
