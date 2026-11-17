"""Suche auf der Webseite (Lupe im Menü, Ralf 05.11.): Startseite, Textseiten,
Untereinheiten, Einleitungen der Bereiche, Alben, Dokumente und Termine.

Gesucht wird nur in dem, was die Webseite ohnehin zeigt: veröffentlichte Texte und
Abschnitte (Startseite und Textseiten, Ralf 14.11.: „Fahnenschwenker“ stand in einer
Kachel und wurde nicht gefunden), die Zeitleiste der Chronik, öffentliche Termine und
sichtbare Alben. Personen, Ansprechpartner und Mitgliederlisten bleiben außen vor, damit
die Suche keine Namen aus anderen Zusammenhängen zusammenträgt. Gefunden wird auch ein
Wortteil, ohne Rücksicht auf Groß- und Kleinschreibung und Akzente („floten“ findet
„Flöten“).
"""

from __future__ import annotations

import re
import unicodedata

from . import gallery
from .content_models import WebsiteText
from .home import UNIT_BUILTINS
from .menu import HISTORY_SLUG, MEMORIAL_SLUG

MIN_QUERY = 2
MAX_QUERY = 100
MAX_RESULTS = 50
SNIPPET = 160

_MARKUP = re.compile(r"!\[[^\]]*\]\([^)]*\)|\[([^\]]*)\]\([^)]*\)|[#>|]+")
# Hervorhebungen fallen ersatzlos weg, damit „**Wort**.“ nicht zu „Wort .“ wird.
_EMPHASIS = re.compile(r"[*_`~]+")


def plain(text: str) -> str:
    """Markdown grob zu Text: Bilder weg, Links als Linktext, Zeichen weg."""
    text = _MARKUP.sub(lambda m: m.group(1) or " ", text or "")
    text = _EMPHASIS.sub("", text)
    return " ".join(text.split())


def _fold_char(c: str) -> str:
    low = c.lower()
    return unicodedata.normalize("NFD", low)[:1] if len(low) == 1 else c


def fold(text: str) -> str:
    """Klein und ohne Akzente, Zeichen für Zeichen (gleiche Länge, für den Ausschnitt)."""
    return "".join(_fold_char(c) for c in text or "")


def terms(query: str) -> list[str]:
    query = " ".join((query or "").split())[:MAX_QUERY]
    if len(query) < MIN_QUERY:
        return []
    return [fold(t) for t in query.split(" ") if t]


def matches(words: list[str], *fields: str) -> bool:
    haystack = fold(" ".join(f or "" for f in fields))
    return all(w in haystack for w in words)


def snippet(text: str, words: list[str]) -> str:
    """Ausschnitt um den ersten Treffer, höchstens ``SNIPPET`` Zeichen."""
    if not text:
        return ""
    low = fold(text)
    hits = [i for w in words if (i := low.find(w)) >= 0]
    start = max(0, min(hits) - SNIPPET // 3) if hits else 0
    part = text[start : start + SNIPPET]
    if start > 0:
        part = "…" + part.split(" ", 1)[-1]
    if start + SNIPPET < len(text):
        part = part.rsplit(" ", 1)[0] + " …"
    return part


# Abschnitte (Startseite und Textseiten): welche Felder auf der Webseite als Text stehen.
# Termine, Alben und Dokumente finden sich über ihre eigenen Treffer; Ansprechpartner
# (Namen) bleiben außen vor.
SECTION_FIELDS = {
    "text": ("title", "text"),
    "text_image": ("title", "text"),
    "banner": ("line",),
    "quote": ("text",),
    "directions": ("title", "text"),
    "video": ("title", "text"),
    "countdown": ("title", "text", "after_text"),
    "join": ("title", "text", "label"),
    "donation": ("title", "text", "purpose"),
    "callout": ("title", "text"),
    "hours": ("title", "text"),
    "program": ("title", "text"),
    "table": ("title", "text"),
    "app": ("title", "text"),
}
SECTION_LISTS = {
    "buttons": ("buttons", ("label",)),
    "tiles": ("tiles", ("title", "text")),
    "faq": ("items", ("question", "answer")),
    "partners": ("items", ("name",)),
    "facts": ("items", ("value", "label")),
    "hours": ("items", ("day", "time", "note")),
    "columns": ("items", ("title", "text")),
    "accordion": ("items", ("title", "text")),
    "timeline": ("items", ("when", "title", "text")),
    "images": ("items", ("caption",)),
    "downloads": ("items", ("label",)),
}


def section_text(section: dict) -> str:
    """Sichtbarer Text eines aufgelösten Abschnitts, als einfacher Text."""
    kind = section.get("kind")
    parts = [section.get(f) for f in SECTION_FIELDS.get(kind, ("title",))]
    if kind in SECTION_LISTS:
        parts.insert(0, section.get("title"))
        key, fields = SECTION_LISTS[kind]
        for item in section.get(key) or []:
            if isinstance(item, dict):
                parts.extend(item.get(f) for f in fields)
    if kind == "table":
        parts.extend(section.get("head") or [])
        for row in section.get("rows") or []:
            parts.extend(row if isinstance(row, list) else [])
    if kind == "program":
        for day in section.get("days") or []:
            parts.append(day.get("day"))
            parts.extend(i.get("text") for i in day.get("items") or [])
    return plain(" ".join(str(p) for p in parts if isinstance(p, str | int) and p))


def _timeline_text(site, t) -> str:
    if not site.chronicle_on:
        return ""
    return plain(" ".join(f"{e['year']} {e['title']} {e['text']}" for e in site.timeline(t)))


INTRO_BLOCK = {"board": "board", "events": "events", "gallery": "gallery", "contact": "contact"}


# Gesamtaudit 15.11., WEB-06: Jede Suche baute alle Texte, Abschnitte, Alben, Dokumente und
# Terminvorkommen neu auf. Jetzt entsteht je Webseite ein Suchindex (Kandidaten mit ihrem Text),
# der INDEX_SECONDS im Zwischenspeicher liegt und beim Veröffentlichen verworfen wird. In der
# Vorschau (Entwurf) wird nie zwischengespeichert.
INDEX_SECONDS = 120


def index_key(website_pk: int, language: str) -> str:
    return f"website:suchindex:{website_pk}:{language}"


def forget_index(website_pk: int) -> None:
    """Nach dem Veröffentlichen: Index aller Sprachen verwerfen."""
    from django.conf import settings
    from django.core.cache import cache

    cache.delete_many([index_key(website_pk, code) for code, _name in settings.LANGUAGES])


def _entry(hit: dict, fields, body: str | None, snip: bool = True) -> dict:
    """Ein Kandidat: ``fields`` zum Vergleich, ``body`` für den Ausschnitt."""
    return {"hit": hit, "fields": [f or "" for f in fields], "body": body or "", "snip": snip}


def build_index(site, events) -> list[dict]:
    """Alle Kandidaten in Reihenfolge Startseite, Textseiten, Untereinheiten, Einleitungen,
    Alben, Dokumente, Termine (wie die Treffer)."""
    website = site.site
    from . import home
    from .public_views import event_entry

    entries: list[dict] = []
    for s in home.public(site, website.home(), event_entry):
        if s["kind"] == "greeting":
            g = site.greeting()
            if not g:
                continue
            title, text = g["title"], plain(g["text"])
        elif not home.is_custom(s["key"]):
            continue  # feste Bausteine (Termine, Majestäten …) finden sich anderswo
        else:
            title, text = s.get("title") or "", section_text(s)
        if text:
            entries.append(
                _entry({"kind": "home", "key": s["key"], "title": title}, [title, text], text)
            )
    texts = site.published_texts().filter(kind=WebsiteText.Kind.PAGE).order_by("published_title")
    for t in texts:
        if t.slug == HISTORY_SLUG and not website.block_on("history"):
            continue
        if t.slug == MEMORIAL_SLUG and not website.block_on("memorial"):
            continue
        body = plain(t.published_body)
        extra = [section_text(s) for s in site.page_sections(t) if s["kind"] != "body"]
        if t.slug == HISTORY_SLUG:
            extra.append(_timeline_text(site, t))
        full = " ".join(p for p in (body, *extra) if p)
        kind = {HISTORY_SLUG: "history", MEMORIAL_SLUG: "memorial"}.get(t.slug, "page")
        entries.append(
            _entry(
                {"kind": kind, "slug": t.slug, "title": t.published_title},
                [t.published_title, full],
                full,
            )
        )
    for u in site.units:
        text = site.unit_text(u)
        title = (text.published_title if text else "") or u.name
        body = plain(text.published_body) if text else ""
        if text is not None and text.published_sections:
            # Eigene Abschnitte der Seite einer Untereinheit (#491)
            extra = [
                section_text(s) for s in site.unit_sections(text) if s["kind"] not in UNIT_BUILTINS
            ]
            body = " ".join(p for p in (body, *extra) if p)
        entries.append(
            _entry(
                {"kind": "unit", "slug": site.unit_slugs[u.pk], "title": title},
                [u.name, u.short_name, title, body],
                body,
            )
        )
    for area, intro in site.intros().items():
        shown = bool(site.units) if area == "units" else website.block_on(INTRO_BLOCK[area])
        body = plain(intro["text"])
        if shown:
            entries.append(
                _entry(
                    {"kind": "intro", "area": area, "title": intro["title"]},
                    [intro["title"], body],
                    body,
                )
            )
    for a in gallery.visible_albums(website).order_by("-date", "title"):
        entries.append(
            _entry(
                {
                    "kind": "album",
                    "slug": a.slug,
                    "title": a.title,
                    "date": a.date.isoformat() if a.date else None,
                },
                [a.title, a.description],
                plain(a.description),
            )
        )
    from .content_models import WebsiteDocument

    for d in WebsiteDocument.objects.filter(website=website, published=True):
        block = "press" if d.section == WebsiteDocument.Section.PRESS else "statutes"
        if website.block_on(block):
            entries.append(
                _entry(
                    {
                        "kind": "press" if block == "press" else "documents",
                        "id": d.key,
                        "title": d.title,
                        "text": d.source,
                        "date": d.date.isoformat() if d.date else None,
                    },
                    [d.title, d.source],
                    None,
                    snip=False,
                )
            )
    if website.block_on("events"):
        seen = set()
        for o in events():
            e = o.event
            if o.is_cancelled or e.pk in seen:
                continue
            seen.add(e.pk)
            entries.append(
                _entry(
                    {"kind": "event", "id": o.key, "title": e.title, "starts_at": o.starts_at},
                    [e.title, e.location, e.description],
                    plain(e.description),
                )
            )
    return entries


def _index(site, events) -> list[dict]:
    from django.core.cache import cache
    from django.utils.translation import get_language

    if getattr(site.site, "draft_shown", False):
        return build_index(site, events)  # Vorschau: Entwurf nie zwischenspeichern
    key = index_key(site.site.pk, get_language() or "de")
    entries = cache.get(key)
    if entries is None:
        entries = build_index(site, events)
        cache.set(key, entries, INDEX_SECONDS)
    return entries


def search(site, query: str, events) -> list[dict]:
    """Treffer in Reihenfolge Startseite, Textseiten, Untereinheiten, Einleitungen, Alben,
    Dokumente, Termine. ``events``: öffentliche Termine (Vorkommen) wie in der Terminliste."""
    words = terms(query)
    if not words:
        return []
    result = []
    for entry in _index(site, events):
        if not matches(words, *entry["fields"]):
            continue
        hit = dict(entry["hit"])
        if entry["snip"]:
            hit["text"] = snippet(entry["body"], words)
        result.append(hit)
        if len(result) >= MAX_RESULTS:
            break
    return result
