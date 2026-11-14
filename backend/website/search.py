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
}
SECTION_LISTS = {
    "buttons": ("buttons", ("label",)),
    "tiles": ("tiles", ("title", "text")),
    "faq": ("items", ("question", "answer")),
    "partners": ("items", ("name",)),
    "facts": ("items", ("value", "label")),
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
    return plain(" ".join(str(p) for p in parts if isinstance(p, str | int) and p))


def _home_hits(site, words, event_entry) -> list[dict]:
    from . import home

    result = []
    for s in home.public(site, site.site.home(), event_entry):
        if s["kind"] == "greeting":
            g = site.greeting()
            if not g:
                continue
            title, text = g["title"], plain(g["text"])
        elif not home.is_custom(s["key"]):
            continue  # feste Bausteine (Termine, Majestäten …) finden sich anderswo
        else:
            title, text = s.get("title") or "", section_text(s)
        if text and matches(words, title, text):
            result.append(
                {"kind": "home", "key": s["key"], "title": title, "text": snippet(text, words)}
            )
    return result


def _timeline_text(site, t) -> str:
    if not site.chronicle_on:
        return ""
    return plain(" ".join(f"{e['year']} {e['title']} {e['text']}" for e in site.timeline(t)))


INTRO_BLOCK = {"board": "board", "events": "events", "gallery": "gallery"}


def search(site, query: str, events) -> list[dict]:
    """Treffer in Reihenfolge Startseite, Textseiten, Untereinheiten, Einleitungen, Alben,
    Dokumente, Termine. ``events``: öffentliche Termine (Vorkommen) wie in der Terminliste."""
    words = terms(query)
    if not words:
        return []
    website = site.site
    from .public_views import event_entry

    result: list[dict] = _home_hits(site, words, event_entry)
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
        if not matches(words, t.published_title, full):
            continue
        kind = {HISTORY_SLUG: "history", MEMORIAL_SLUG: "memorial"}.get(t.slug, "page")
        result.append(
            {"kind": kind, "slug": t.slug, "title": t.published_title, "text": snippet(full, words)}
        )
    for u in site.units:
        text = site.unit_text(u)
        title = (text.published_title if text else "") or u.name
        body = plain(text.published_body) if text else ""
        if matches(words, u.name, u.short_name, title, body):
            result.append(
                {
                    "kind": "unit",
                    "slug": site.unit_slugs[u.pk],
                    "title": title,
                    "text": snippet(body, words),
                }
            )
    for area, intro in site.intros().items():
        shown = bool(site.units) if area == "units" else website.block_on(INTRO_BLOCK[area])
        body = plain(intro["text"])
        if shown and matches(words, intro["title"], body):
            result.append(
                {
                    "kind": "intro",
                    "area": area,
                    "title": intro["title"],
                    "text": snippet(body, words),
                }
            )
    for a in gallery.visible_albums(website).order_by("-date", "title"):
        if matches(words, a.title, a.description):
            result.append(
                {
                    "kind": "album",
                    "slug": a.slug,
                    "title": a.title,
                    "text": snippet(plain(a.description), words),
                    "date": a.date.isoformat() if a.date else None,
                }
            )
    from .content_models import WebsiteDocument

    for d in WebsiteDocument.objects.filter(website=website, published=True):
        block = "press" if d.section == WebsiteDocument.Section.PRESS else "statutes"
        if website.block_on(block) and matches(words, d.title, d.source):
            result.append(
                {
                    "kind": "press" if block == "press" else "documents",
                    "id": d.key,
                    "title": d.title,
                    "text": d.source,
                    "date": d.date.isoformat() if d.date else None,
                }
            )
    if website.block_on("events"):
        seen = set()
        for o in events():
            e = o.event
            if o.is_cancelled or e.pk in seen:
                continue
            if matches(words, e.title, e.location, e.description):
                seen.add(e.pk)
                result.append(
                    {
                        "kind": "event",
                        "id": o.key,
                        "title": e.title,
                        "text": snippet(plain(e.description), words),
                        "starts_at": o.starts_at,
                    }
                )
    return result[:MAX_RESULTS]
