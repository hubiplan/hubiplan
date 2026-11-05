"""Suche auf der Webseite (Lupe im Menü, Ralf 05.11.): Textseiten, Alben, Dokumente
und Termine.

Gesucht wird nur in dem, was die Webseite ohnehin zeigt: veröffentlichte Texte,
öffentliche Termine und sichtbare Alben. Personen und Mitgliederlisten bleiben außen
vor, damit die Suche keine Namen aus anderen Zusammenhängen zusammenträgt.
"""

from __future__ import annotations

import re

from . import gallery
from .content_models import WebsiteText
from .menu import HISTORY_SLUG, MEMORIAL_SLUG

MIN_QUERY = 2
MAX_QUERY = 100
MAX_RESULTS = 50
SNIPPET = 160

_MARKUP = re.compile(r"!\[[^\]]*\]\([^)]*\)|\[([^\]]*)\]\([^)]*\)|[#*_>`|~]+")


def plain(text: str) -> str:
    """Markdown grob zu Text: Bilder weg, Links als Linktext, Zeichen weg."""
    text = _MARKUP.sub(lambda m: m.group(1) or " ", text or "")
    return " ".join(text.split())


def terms(query: str) -> list[str]:
    query = " ".join((query or "").split())[:MAX_QUERY]
    if len(query) < MIN_QUERY:
        return []
    return [t.casefold() for t in query.split(" ") if t]


def matches(words: list[str], *fields: str) -> bool:
    haystack = " ".join(f or "" for f in fields).casefold()
    return all(w in haystack for w in words)


def snippet(text: str, words: list[str]) -> str:
    """Ausschnitt um den ersten Treffer, höchstens ``SNIPPET`` Zeichen."""
    if not text:
        return ""
    low = text.casefold()
    hits = [i for w in words if (i := low.find(w)) >= 0]
    start = max(0, min(hits) - SNIPPET // 3) if hits else 0
    part = text[start : start + SNIPPET]
    if start > 0:
        part = "…" + part.split(" ", 1)[-1]
    if start + SNIPPET < len(text):
        part = part.rsplit(" ", 1)[0] + " …"
    return part


def search(site, query: str, events) -> list[dict]:
    """Treffer in Reihenfolge Textseiten, Alben, Dokumente, Termine. ``events``: öffentliche Termine
    (Vorkommen) wie in der Terminliste."""
    words = terms(query)
    if not words:
        return []
    website = site.site
    result: list[dict] = []
    texts = site.published_texts().filter(kind=WebsiteText.Kind.PAGE).order_by("published_title")
    for t in texts:
        if t.slug == HISTORY_SLUG and not website.block_on("history"):
            continue
        if t.slug == MEMORIAL_SLUG and not website.block_on("memorial"):
            continue
        body = plain(t.published_body)
        if not matches(words, t.published_title, body):
            continue
        kind = {HISTORY_SLUG: "history", MEMORIAL_SLUG: "memorial"}.get(t.slug, "page")
        result.append(
            {"kind": kind, "slug": t.slug, "title": t.published_title, "text": snippet(body, words)}
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
