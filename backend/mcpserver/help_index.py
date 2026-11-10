"""Hilfe und Begriffe für die KI-Schnittstelle (Stufe 0, docs/mcp.md).

Quelle ist ``hilfe.json`` neben dieser Datei: eine Kopie der Markdown-Hilfe aus
``frontend/src/help`` und der Begriffe der Lernhilfen. Erzeugt wird sie mit
``node scripts/mcp-hilfe.mjs`` im Ordner ``frontend``; der Test ``McpHilfe.test.ts``
meldet, wenn sie veraltet ist. Hier wird nur gelesen, gesucht und aufbereitet:
Platzhalter wie ``{pl}`` mit den Standardwörtern gefüllt, Bilder durch ihren
Alternativtext ersetzt. Vereinsdaten kommen nicht vor.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from django.utils import translation
from django.utils.translation import gettext as _

from organizations import terms as org_terms

DATA_FILE = Path(__file__).with_name("hilfe.json")
LANGS = ("de", "en")

_HEAD = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)
_IMAGE = re.compile(r"!\[([^\]]*)\]\(bild:[^)]*\)")
_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_WORD = re.compile(r"\w+")


@dataclass(frozen=True)
class HelpEntry:
    slug: str
    key: str
    kind: str  # "guide" (Anleitung) oder "page" (Seitenhilfe)
    title: str
    keywords: tuple[str, ...]
    body: str


@dataclass(frozen=True)
class GlossaryEntry:
    key: str
    kind: str  # "term" oder "decision"
    name: str
    text: str
    example: str
    section: str


@lru_cache(maxsize=1)
def _raw() -> dict:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def _list(value: str) -> tuple[str, ...]:
    value = value.strip()
    if not (value.startswith("[") and value.endswith("]")):
        return ()
    return tuple(s.strip() for s in value[1:-1].split(",") if s.strip())


def _slug(name: str) -> str:
    slug = name.removesuffix(".md")
    if slug.startswith("seiten/"):
        return "seite/" + slug.removeprefix("seiten/")
    return slug.removeprefix("anleitungen/")


def _terms() -> dict[str, str]:
    return {
        **org_terms.default_fed_terms(),
        **org_terms.default_own_terms(),
        **org_terms.default_dept_terms(),
    }


def _terms_and_image(lang: str) -> dict[str, str]:
    with translation.override(lang):
        # Bildschirmfotos gibt es hier nicht; ihr Alternativtext bleibt als Hinweis
        return {**_terms(), "__bild__": _("Bild")}


def _clean(text: str, terms: dict[str, str]) -> str:
    text = _PLACEHOLDER.sub(lambda m: terms.get(m[1], m[0]), text)
    image = terms.get("__bild__", "Bild")
    return _IMAGE.sub(lambda m: f"({image}: {m[1]})" if m[1] else "", text)


def parse(name: str, raw: str, terms: dict[str, str]) -> HelpEntry | None:
    m = _HEAD.match(raw)
    if not m:
        return None
    meta: dict[str, str] = {}
    for line in re.sub(r"\n[ \t]+", " ", m[1]).split("\n"):
        kv = re.match(r"^([a-z]+):\s*(.*)$", line)
        if kv:
            meta[kv[1]] = kv[2].strip()
    key = meta.get("key", "")
    if not meta.get("titel") or not key:
        return None
    return HelpEntry(
        slug=_slug(name),
        key=key,
        kind="page" if key.startswith("page.") else "guide",
        title=_clean(meta["titel"], terms),
        keywords=tuple(_clean(k, terms) for k in _list(meta.get("stichworte", ""))),
        body=_clean(m[2].strip(), terms),
    )


def _lang(lang: str) -> str:
    return lang if lang in LANGS else "de"


@lru_cache(maxsize=len(LANGS))
def help_entries(lang: str = "de") -> tuple[HelpEntry, ...]:
    """Alle Einträge einer Sprache; fehlt eine englische Datei, gilt die deutsche."""
    lang = _lang(lang)
    data = _raw()["help"]
    terms = _terms_and_image(lang)
    entries = []
    for name, raw in data["de"].items():
        entry = parse(name, data[lang].get(name, raw), terms)
        if entry:
            entries.append(entry)
    return tuple(sorted(entries, key=lambda e: (e.kind, e.title.casefold())))


@lru_cache(maxsize=len(LANGS))
def glossary(lang: str = "de") -> tuple[GlossaryEntry, ...]:
    lang = _lang(lang)
    terms = _terms_and_image(lang)
    return tuple(
        GlossaryEntry(
            key=item["key"],
            kind=item["kind"],
            name=_clean(item["name"], terms),
            text=_clean(item["text"], terms),
            example=_clean(item["example"], terms),
            section=_clean(item["section"], terms),
        )
        for item in _raw()["glossary"][lang]
    )


def find(slug: str, lang: str = "de") -> HelpEntry | None:
    slug = slug.strip().strip("/").removeprefix("hilfe/")
    for entry in help_entries(lang):
        if entry.slug == slug or entry.key == slug:
            return entry
    return None


def _words(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.casefold()) if len(w) > 1]


def _score(words: list[str], weighted: list[tuple[str, int]]) -> int:
    score = 0
    for word in words:
        hit = 0
        for text, weight in weighted:
            if word in text:
                hit = max(hit, weight)
        score += hit
    return score


def search_help(query: str, lang: str = "de", limit: int = 5) -> list[HelpEntry]:
    words = _words(query)
    if not words:
        return []
    scored = []
    for entry in help_entries(lang):
        score = _score(
            words,
            [
                (entry.title.casefold(), 6),
                (" ".join(entry.keywords).casefold(), 4),
                (entry.body.casefold(), 1),
            ],
        )
        if score:
            # Anleitungen vor Seitenhilfen bei gleicher Wertung
            scored.append((-score, entry.kind != "guide", entry.title.casefold(), entry))
    scored.sort(key=lambda s: s[:3])
    return [s[3] for s in scored[:limit]]


def search_glossary(query: str, lang: str = "de", limit: int = 3) -> list[GlossaryEntry]:
    words = _words(query)
    if not words:
        return []
    scored = []
    for entry in glossary(lang):
        score = _score(words, [(entry.name.casefold(), 6), (entry.text.casefold(), 1)])
        if score:
            scored.append((-score, entry.name.casefold(), entry))
    scored.sort(key=lambda s: s[:2])
    return [s[2] for s in scored[:limit]]


def summary(entry: HelpEntry, length: int = 280) -> str:
    """Erster Absatz ohne Überschrift, gekürzt."""
    for block in entry.body.split("\n\n"):
        block = " ".join(block.split())
        if block and not block.startswith("#"):
            return block if len(block) <= length else block[: length - 1].rstrip() + "…"
    return ""
