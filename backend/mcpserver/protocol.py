"""JSON-RPC-Nachrichten des Model Context Protocol (MCP), nur was Stufe 0 braucht.

Ohne Sitzungen und ohne Server-Nachrichten: Jede Anfrage bekommt genau eine
JSON-Antwort (Transport „Streamable HTTP“ erlaubt das). Angeboten werden nur
Werkzeuge (``tools/list``, ``tools/call``), siehe ``tools.py``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from django.utils import translation
from django.utils.translation import gettext as _

from core.version import running_version

from .help_index import LANGS
from .tools import TOOLS, Context, Tool, ToolError

# Neueste zuerst; eine unbekannte Fassung des Clients beantworten wir mit der neuesten
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602


def error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _result(msg_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


@dataclass(frozen=True)
class Server:
    """Eine Adresse der KI-Schnittstelle: Name, Hinweise für den Assistenten, Werkzeuge."""

    name: str
    title: Callable[[], str]
    instructions: Callable[[], str]
    tools: Callable[[Context], Sequence[Tool]]


HELP = Server(
    name="hubiplan-hilfe",
    title=lambda: _("HUBIplan-Hilfe"),
    instructions=lambda: _(
        "Hilfe zu HUBIplan, einer freien Vereinsverwaltung: Anleitungen, Seitenhilfen "
        "und Begriffe. Erst mit hilfe_suchen suchen, dann mit hilfe_lesen den ganzen Text "
        "holen und die Adresse der Anleitung nennen. Die Werkzeuge sehen keine "
        "Vereinsdaten und ändern nichts."
    ),
    tools=lambda ctx: TOOLS,
)


def _initialize(params: dict, server: Server) -> dict:
    wanted = params.get("protocolVersion")
    version = wanted if wanted in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
    return {
        "protocolVersion": version,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {
            "name": server.name,
            "title": server.title(),
            "version": running_version() or "0",
        },
        "instructions": server.instructions(),
    }


def _call(params: dict, ctx: Context, server: Server) -> dict:
    tool = {t.name: t for t in server.tools(ctx)}.get(params.get("name"))
    if tool is None:
        raise LookupError
    args = params.get("arguments") or {}
    if not isinstance(args, dict):
        raise LookupError
    lang = args.get("sprache")
    try:
        # Antwort in der gewünschten Sprache, auch die Hinweise und Fehler
        with translation.override(lang if lang in LANGS else translation.get_language()):
            text, failed = tool.run(args, ctx), False
    except ToolError as exc:
        text, failed = str(exc), True
    return {"content": [{"type": "text", "text": text}], "isError": failed}


def handle(message, ctx: Context, server: Server = HELP) -> dict | None:
    """Eine Nachricht beantworten. ``None``: keine Antwort (Benachrichtigung, Antwort)."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return error(None, INVALID_REQUEST, "Invalid Request")
    msg_id = message.get("id")
    method = message.get("method")
    if not isinstance(method, str):
        # Antworten des Clients auf Anfragen, die wir nie stellen
        return (
            None
            if "result" in message or "error" in message
            else error(msg_id, INVALID_REQUEST, "Invalid Request")
        )
    if "id" not in message:
        return None  # Benachrichtigung, z. B. notifications/initialized
    if not isinstance(msg_id, (str, int)) or isinstance(msg_id, bool):
        return error(None, INVALID_REQUEST, "Invalid Request")
    params = message.get("params") or {}
    if not isinstance(params, dict):
        return error(msg_id, INVALID_PARAMS, "Invalid params")
    if method == "initialize":
        return _result(msg_id, _initialize(params, server))
    if method == "ping":
        return _result(msg_id, {})
    if method == "tools/list":
        return _result(msg_id, {"tools": [tool.describe() for tool in server.tools(ctx)]})
    if method == "tools/call":
        try:
            return _result(msg_id, _call(params, ctx, server))
        except LookupError:
            return error(msg_id, INVALID_PARAMS, "Unknown tool or invalid arguments")
    return error(msg_id, METHOD_NOT_FOUND, "Method not found")
