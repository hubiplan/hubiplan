"""Lesbare Beschreibung der API für andere Programme unter ``/api/partner/v1/docs/``.

Ohne Anmeldung, wie die OpenAPI-Datei, aus der sie erzeugt wird. Sie wird auf dem Server
gebaut und lädt nichts von fremden Servern (kein Swagger/Redoc vom CDN, kein Skript):
Wer keinen Zugang zur Oberfläche hat, etwa der Entwickler beim Dachverband, kann hier lesen,
was die Schnittstelle kann, und die Datei für eigene Werkzeuge herunterladen.
"""

from __future__ import annotations

import re
from functools import lru_cache
from html import escape

from django.conf import settings
from django.http import Http404, HttpResponse
from django.utils import translation
from django.utils.translation import gettext as _
from django.views import View

from . import openapi

DOCS_URL = "https://github.com/hubiplan/hubiplan/blob/main/docs/api.md"
METHODS = ("get", "post", "put", "patch", "delete")
LANGS = ("de", "en")

STYLE = """
body{margin:0;font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;color:#1d2433;
background:#f6f7f9}
main{max-width:960px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.8rem;margin:0 0 .25rem}h2{margin-top:2.5rem;border-bottom:1px solid #d5d9e0;
padding-bottom:.25rem}h3{margin:0 0 .5rem;font-size:1.1rem}
a{color:#1f5fbf;text-decoration:none;font-weight:600}
code{font:.9em/1.4 ui-monospace,SFMono-Regular,Consolas,monospace;background:#eceff4;
padding:.05em .3em;border-radius:4px;overflow-wrap:anywhere}
.lead{color:#4a5468}.links{display:flex;flex-wrap:wrap;gap:.5rem 1.25rem;margin:1rem 0}
.op,.schema{background:#fff;border:1px solid #d5d9e0;border-radius:8px;padding:16px;
margin:12px 0}
.method{display:inline-block;min-width:4.2em;text-align:center;font:700 .8rem/1.8 ui-monospace,
monospace;border-radius:4px;color:#fff;background:#2f6f3e;margin-right:.5rem}
.method.post{background:#1f5fbf}.method.patch{background:#8a5a00}.method.put{background:#8a5a00}
.method.delete{background:#a02828}
.path{font:600 1rem ui-monospace,monospace;overflow-wrap:anywhere}
.scope{color:#4a5468;font-size:.9rem;margin:.25rem 0 .5rem}
table{border-collapse:collapse;width:100%;font-size:.92rem;margin:.5rem 0}
th,td{text-align:left;vertical-align:top;border-top:1px solid #e3e6eb;padding:.35rem .5rem}
th{background:#f0f2f5;font-weight:600}
.req{color:#a02828;font-weight:600}
.toc{columns:2 18rem;padding-left:1.2rem}.toc li{break-inside:avoid}
.muted{color:#4a5468}
@media (prefers-color-scheme:dark){body{background:#14181f;color:#e3e7ee}
.op,.schema{background:#1c222c;border-color:#323a47}th{background:#242b36}
th,td{border-color:#323a47}code{background:#2a313d}a{color:#8db8ff}
.lead,.scope,.muted{color:#a9b2c1}h2{border-color:#323a47}}
"""


def _inline(text: str) -> str:
    """Wenig Markdown: `Code`, ``Code``, **fett**; alles andere wird nur maskiert."""
    out = escape(text, quote=False)
    out = re.sub(r"``(.+?)``", r"<code>\1</code>", out)
    out = re.sub(r"`(.+?)`", r"<code>\1</code>", out)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)


def _block(text: str) -> str:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    html = []
    for part in parts:
        lines = part.splitlines()
        if all(line.lstrip().startswith("* ") for line in lines):
            items = "".join(f"<li>{_inline(line.lstrip()[2:])}</li>" for line in lines)
            html.append(f"<ul>{items}</ul>")
        else:
            html.append(f"<p>{_inline(' '.join(line.strip() for line in lines))}</p>")
    return "".join(html)


def _ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def _type(schema: dict | None) -> str:
    """Typ eines Feldes als kurzer Text, Verweise als Link zum Schema unten."""
    if not schema:
        return ""
    if "$ref" in schema:
        name = _ref_name(schema["$ref"])
        text = f'<a href="#schema-{escape(name)}">{escape(name)}</a>'
    elif schema.get("allOf") and len(schema["allOf"]) == 1:
        text = _type(schema["allOf"][0])
    elif schema.get("type") == "array":
        text = _("Liste von %(item)s") % {"item": _type(schema.get("items"))}
    else:
        text = escape(str(schema.get("type", "object")))
        if schema.get("format"):
            text += f" ({escape(str(schema['format']))})"
    if schema.get("enum"):
        text += ": " + ", ".join(f"<code>{escape(str(v))}</code>" for v in schema["enum"])
    if schema.get("maxLength"):
        text += " " + _("bis %(n)s Zeichen") % {"n": schema["maxLength"]}
    if schema.get("nullable"):
        text += ", " + _("auch null")
    return text


def _parameters(op: dict) -> str:
    params = op.get("parameters") or []
    if not params:
        return ""
    rows = "".join(
        "<tr>"
        f"<td><code>{escape(p['name'])}</code>"
        f"{' <span class=req>*</span>' if p.get('required') else ''}</td>"
        f"<td>{escape(p.get('in', ''))}</td>"
        f"<td>{_type(p.get('schema'))}</td>"
        f"<td>{_inline(p.get('description', ''))}</td>"
        "</tr>"
        for p in params
    )
    return (
        f"<h4>{_('Parameter')}</h4><table><tr><th>{_('Name')}</th><th>{_('Ort')}</th>"
        f"<th>{_('Typ')}</th><th>{_('Bedeutung')}</th></tr>{rows}</table>"
    )


def _body(op: dict) -> str:
    content = (op.get("requestBody") or {}).get("content") or {}
    schema = (content.get("application/json") or {}).get("schema")
    if not schema:
        return ""
    return f"<p><strong>{_('Inhalt (JSON)')}:</strong> {_type(schema)}</p>"


def _responses(op: dict) -> str:
    items = []
    for code, response in sorted((op.get("responses") or {}).items()):
        content = (response.get("content") or {}).get("application/json") or {}
        text = _type(content.get("schema")) if content else ""
        if response.get("description"):
            text = (text + " " if text else "") + _inline(response["description"])
        items.append(f"<li><code>{escape(code)}</code> {text}</li>")
    if not items:
        return ""
    return f"<h4>{_('Antworten')}</h4><ul>{''.join(items)}</ul>"


def _operation(path: str, method: str, op: dict) -> str:
    anchor = escape(op.get("operationId") or f"{method}-{path}")
    scope = op.get("x-scope")
    scope_html = (
        f'<div class="scope">{_("Bereich")}: <code>{escape(scope)}</code></div>' if scope else ""
    )
    description = re.sub(r"\n\nBereich: `[^`]*`\s*$", "", op.get("description", ""))
    return (
        f'<section class="op" id="{anchor}">'
        f"<h3>{escape(op.get('summary') or path)}</h3>"
        f'<div><span class="method {method}">{method.upper()}</span>'
        f'<span class="path">{escape(path)}</span></div>'
        f"{scope_html}{_block(description)}{_parameters(op)}{_body(op)}{_responses(op)}"
        "</section>"
    )


def _schema(name: str, schema: dict) -> str:
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    if props:
        rows = "".join(
            "<tr>"
            f"<td><code>{escape(field)}</code>"
            f"{' <span class=req>*</span>' if field in required else ''}</td>"
            f"<td>{_type(prop)}</td><td>{_inline(prop.get('description', ''))}</td>"
            "</tr>"
            for field, prop in sorted(props.items())
        )
        body = (
            f"<table><tr><th>{_('Feld')}</th><th>{_('Typ')}</th>"
            f"<th>{_('Bedeutung')}</th></tr>{rows}</table>"
        )
    else:
        body = f"<p>{_type(schema)}</p>"
    return (
        f'<section class="schema" id="schema-{escape(name)}"><h3>{escape(name)}</h3>'
        f"{body}</section>"
    )


@lru_cache(maxsize=len(LANGS))
def render(lang: str) -> str:
    spec = openapi.build()
    with translation.override(lang):
        operations = [
            (path, method, item[method])
            for path, item in spec.get("paths", {}).items()
            for method in METHODS
            if method in item
        ]
        toc = "".join(
            f'<li><a href="#{escape(op.get("operationId") or f"{m}-{p}")}">'
            f"{escape(op.get('summary') or p)}</a> <code>{m.upper()} {escape(p)}</code></li>"
            for p, m, op in operations
        )
        german_only = _("Die Beschreibungen der einzelnen Aufrufe sind auf Deutsch.")
        note = f'<p class="muted">{german_only}</p>' if lang != "de" else ""
        other = "en" if lang == "de" else "de"
        other_label = "English" if other == "en" else "Deutsch"
        schemas = "".join(
            _schema(name, schema)
            for name, schema in sorted(spec.get("components", {}).get("schemas", {}).items())
        )
        return (
            f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="robots" content="noindex">'
            f"<title>{_('HUBIplan API für andere Programme')}</title>"
            f"<style>{STYLE}</style></head><body><main>"
            f"<h1>{_('HUBIplan API für andere Programme')}</h1>"
            f'<p class="lead">{_("Version")} {escape(str(spec["info"].get("version", "")))}. '
            f"{_('Diese Seite beschreibt die Schnittstelle dieser HUBIplan-Instanz. Den Schlüssel vergibt der Vorstand einer Einheit unter Einstellungen › API-Zugänge.')}</p>"  # noqa: E501
            '<div class="links">'
            f'<a href="../openapi.json">{_("OpenAPI-Beschreibung (JSON)")}</a>'
            f'<a href="{DOCS_URL}" rel="noopener">{_("Ausführliche Anleitung (docs/api.md)")}</a>'
            f'<a href="?lang={other}" hreflang="{other}">{other_label}</a>'
            "</div>"
            f"{note}"
            f"<h2>{_('Überblick')}</h2>{_block(spec['info'].get('description', ''))}"
            f"<h2>{_('Aufrufe')}</h2><ul class='toc'>{toc}</ul>"
            + "".join(_operation(p, m, op) for p, m, op in operations)
            + f"<h2>{_('Datenformen')}</h2>"
            f'<p class="muted">{_("Mit * markierte Felder sind immer vorhanden bzw. Pflicht.")}</p>'
            f"{schemas}</main></body></html>"
        )


def _language(request) -> str:
    wanted = request.GET.get("lang")
    if wanted in LANGS:
        return wanted
    for part in request.headers.get("Accept-Language", "").split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in LANGS:
            return code
    return "de"


class DocsView(View):
    """Lesbare Seite zur OpenAPI-Beschreibung, ohne Anmeldung und ohne fremde Inhalte."""

    def get(self, request):
        if not settings.PARTNER_API_ENABLED:
            raise Http404
        response = HttpResponse(render(_language(request)), content_type="text/html; charset=utf-8")
        response["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; "
            "form-action 'none'; frame-ancestors 'none'"
        )
        response["Cache-Control"] = "public, max-age=3600"
        response["Vary"] = "Accept-Language"
        return response
