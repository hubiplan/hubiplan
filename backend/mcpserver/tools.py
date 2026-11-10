"""Werkzeuge der KI-Schnittstelle, Stufe 0: nur die HUBIplan-Hilfe (docs/mcp.md).

Jedes Werkzeug liest nur, hat keine Nebenwirkung und sieht keine Vereinsdaten.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from . import help_index

LANG_SCHEMA = {
    "type": "string",
    "enum": list(help_index.LANGS),
    "default": "de",
    "description": gettext_lazy("Sprache der Antwort: de (Deutsch) oder en (Englisch)."),
}
MAX_QUERY = 200


class ToolError(Exception):
    """Fehler, den das Werkzeug dem Assistenten als Text zurückgibt (isError)."""


@dataclass(frozen=True)
class Tool:
    name: str
    title: object
    description: object
    schema: dict
    run: Callable[[dict, Callable[[str], str]], str]

    def describe(self) -> dict:
        return {
            "name": self.name,
            "title": str(self.title),
            "description": str(self.description),
            "inputSchema": _resolve(self.schema),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }


def _resolve(value):
    """gettext_lazy in Schemas zu Text machen (in der Sprache der Anfrage)."""
    if isinstance(value, dict):
        return {k: _resolve(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _text(args: dict, name: str, required: bool = True) -> str:
    value = args.get(name, "")
    if not isinstance(value, str):
        raise ToolError(_("„%(name)s“ muss ein Text sein.") % {"name": name})
    value = value.strip()
    if required and not value:
        raise ToolError(_("„%(name)s“ fehlt.") % {"name": name})
    if len(value) > MAX_QUERY:
        raise ToolError(_("„%(name)s“ ist zu lang (höchstens 200 Zeichen).") % {"name": name})
    return value


def _lang(args: dict) -> str:
    lang = args.get("sprache", "de")
    if lang not in help_index.LANGS:
        raise ToolError(_("Sprache muss de oder en sein."))
    return lang


def _count(args: dict, default: int, maximum: int) -> int:
    value = args.get("anzahl", default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolError(_("„anzahl“ muss eine ganze Zahl sein."))
    return max(1, min(value, maximum))


def _search(args: dict, link: Callable[[str], str]) -> str:
    query = _text(args, "frage")
    lang = _lang(args)
    hits = help_index.search_help(query, lang, _count(args, 5, 10))
    if not hits:
        return _(
            "Keine passende Anleitung gefunden. Andere Wörter versuchen oder "
            "hilfe_uebersicht aufrufen."
        )
    lines = []
    for n, entry in enumerate(hits, 1):
        lines.append(f"{n}. {entry.title} ({_('Name')}: {entry.slug})")
        lines.append(f"   {link(entry.slug)}")
        text = help_index.summary(entry)
        if text:
            lines.append(f"   {text}")
    lines.append("")
    lines.append(_("Den ganzen Text liefert hilfe_lesen mit dem Namen."))
    return "\n".join(lines)


def _read(args: dict, link: Callable[[str], str]) -> str:
    entry = help_index.find(_text(args, "name"), _lang(args))
    if entry is None:
        raise ToolError(_("Diese Anleitung gibt es nicht. Erst mit hilfe_suchen suchen."))
    kind = _("Anleitung") if entry.kind == "guide" else _("Seitenhilfe")
    return f"# {entry.title}\n\n{kind} · {link(entry.slug)}\n\n{entry.body}\n\n" + _(
        "Links wie (/mitglieder) sind Seiten in HUBIplan, relativ zur Adresse der "
        "Instanz. Was jemand davon sieht, hängt von Rechten und Modulen ab."
    )


def _overview(args: dict, link: Callable[[str], str]) -> str:
    lang = _lang(args)
    kind = args.get("art", "anleitungen")
    if kind not in ("anleitungen", "seiten"):
        raise ToolError(_("„art“ muss anleitungen oder seiten sein."))
    wanted = "guide" if kind == "anleitungen" else "page"
    entries = [e for e in help_index.help_entries(lang) if e.kind == wanted]
    return "\n".join(f"- {e.title} ({e.slug})" for e in entries)


def _glossary(args: dict, link: Callable[[str], str]) -> str:
    hits = help_index.search_glossary(_text(args, "begriff"), _lang(args), 3)
    if not hits:
        return _("Diesen Begriff kennt das Glossar nicht. hilfe_suchen versuchen.")
    blocks = []
    for entry in hits:
        lines = [f"## {entry.name}"]
        if entry.section:
            lines.append(entry.section)
        lines.append(entry.text)
        if entry.example:
            lines.append(entry.example)
        blocks.append("\n".join(lines))
    blocks.append(link("begriffe"))
    return "\n\n".join(blocks)


TOOLS: tuple[Tool, ...] = (
    Tool(
        name="hilfe_suchen",
        title=gettext_lazy("Hilfe durchsuchen"),
        description=gettext_lazy(
            "Sucht in der Hilfe von HUBIplan (Vereinsverwaltung) nach Anleitungen und "
            "Seitenhilfen, z. B. „Mitglied aufnehmen“ oder „Rundschreiben senden“. Liefert "
            "Titel, Name, Adresse und eine kurze Beschreibung. Enthält keine Vereinsdaten."
        ),
        schema={
            "type": "object",
            "properties": {
                "frage": {
                    "type": "string",
                    "description": gettext_lazy("Wonach gesucht wird, in Stichworten."),
                    "maxLength": MAX_QUERY,
                },
                "sprache": LANG_SCHEMA,
                "anzahl": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 5,
                    "description": gettext_lazy("Höchstzahl der Treffer."),
                },
            },
            "required": ["frage"],
            "additionalProperties": False,
        },
        run=_search,
    ),
    Tool(
        name="hilfe_lesen",
        title=gettext_lazy("Anleitung lesen"),
        description=gettext_lazy(
            "Liefert den ganzen Text einer Anleitung oder Seitenhilfe von HUBIplan als "
            "Markdown. Den Namen liefern hilfe_suchen oder hilfe_uebersicht."
        ),
        schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": gettext_lazy(
                        "Name der Anleitung, z. B. passwort-aendern oder seite/mein-konto."
                    ),
                    "maxLength": MAX_QUERY,
                },
                "sprache": LANG_SCHEMA,
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        run=_read,
    ),
    Tool(
        name="hilfe_uebersicht",
        title=gettext_lazy("Alle Anleitungen"),
        description=gettext_lazy(
            "Listet alle Anleitungen (art=anleitungen) oder alle Seitenhilfen (art=seiten) "
            "der HUBIplan-Hilfe mit Namen."
        ),
        schema={
            "type": "object",
            "properties": {
                "art": {
                    "type": "string",
                    "enum": ["anleitungen", "seiten"],
                    "default": "anleitungen",
                    "description": gettext_lazy("Anleitungen oder Seitenhilfen."),
                },
                "sprache": LANG_SCHEMA,
            },
            "additionalProperties": False,
        },
        run=_overview,
    ),
    Tool(
        name="begriff_erklaeren",
        title=gettext_lazy("Begriff erklären"),
        description=gettext_lazy(
            "Erklärt einen Begriff aus der Vereinsverwaltung oder eine Entscheidung in "
            "HUBIplan aus dem Glossar, z. B. „Mitgliedsart“, „SEPA-Mandat“ oder „Kassenprüfung“."
        ),
        schema={
            "type": "object",
            "properties": {
                "begriff": {
                    "type": "string",
                    "description": gettext_lazy("Der Begriff."),
                    "maxLength": MAX_QUERY,
                },
                "sprache": LANG_SCHEMA,
            },
            "required": ["begriff"],
            "additionalProperties": False,
        },
        run=_glossary,
    ),
)

TOOL_BY_NAME = {tool.name: tool for tool in TOOLS}
