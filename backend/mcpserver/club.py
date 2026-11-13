"""Werkzeuge für die Vereinsdaten, Stufe W1: Webseite lesen und als Entwurf bearbeiten.

Gestaltung, Menü, Aufbau der Startseite, Bilder und Beitragsentwürfe (W2/W3) stehen in
``club_design``.

Die Werkzeuge rufen dieselben Ansichten auf wie die Oberfläche im Browser
(``website.views``, ``website.content_views``). Rechte, Prüfungen, Protokoll und
„Rückgängig“ sind also dieselben; der Assistent darf nie mehr als die Person, die ihn
verbunden hat. Es gibt bewusst kein Werkzeug zum Veröffentlichen, für Zustand, Domains
oder Kontaktnachrichten (docs/mcp.md).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import RequestFactory
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from rest_framework import authentication

from .oauth import SCOPE_DRAFT, SCOPE_READ
from .tools import LANG_SCHEMA, TOOLS, Context, Tool, ToolError

logger = logging.getLogger(__name__)

MAX_BODY = 50_000
MAX_TITLE = 200


class _GrantAuthentication(authentication.BaseAuthentication):
    """Innere Anfrage eines Werkzeugs: die Person hinter der Verbindung."""

    def authenticate(self, request):
        grant = getattr(request._request, "mcp_grant", None)
        if grant is None:
            return None
        return grant.user, grant


_VIEWS: dict[type, type] = {}


def _for_mcp(view_cls: type) -> type:
    if view_cls not in _VIEWS:
        _VIEWS[view_cls] = type(
            f"Mcp{view_cls.__name__}",
            (view_cls,),
            {
                "__module__": __name__,
                "authentication_classes": [_GrantAuthentication],
                "throttle_classes": [],
            },
        )
    return _VIEWS[view_cls]


@dataclass
class ClubContext(Context):
    request: object = None
    grant: object = None

    @property
    def org_id(self) -> int:
        return self.grant.organization_id

    def call(self, view_cls: type, method: str, path: str, data=None, multipart=None, **kwargs):
        """Ansicht der Oberfläche aufrufen; liefert die Daten der Antwort oder ToolError.

        ``multipart``: Formular mit Dateien (POST), z. B. für das Logo."""
        outer = self.request
        factory = RequestFactory()
        extra = {
            "HTTP_HOST": outer.get_host(),
            "REMOTE_ADDR": outer.META.get("REMOTE_ADDR", ""),
            "secure": outer.is_secure(),
        }
        full = f"/api/orgs/{self.org_id}/{path}"
        if method == "GET":
            inner = factory.get(full, **extra)
        elif multipart is not None:
            inner = factory.post(full, multipart, **extra)
        else:
            inner = factory.generic(
                method,
                full,
                json.dumps(data or {}),
                content_type="application/json",
                **extra,
            )
        inner.mcp_grant = self.grant
        inner.user = self.grant.user
        inner.session = SessionStore()
        inner.LANGUAGE_CODE = getattr(outer, "LANGUAGE_CODE", "de")
        view = _for_mcp(view_cls).as_view()
        response = view(inner, org_id=self.org_id, **kwargs)
        status = response.status_code
        body = getattr(response, "data", None)
        if status >= 400:
            raise ToolError(_problem(status, body))
        return body


def _problem(status: int, body) -> str:
    if status == 404:
        return _(
            "Nicht gefunden oder nicht erlaubt (Modul „Webseite“ aus, Recht fehlt oder "
            "unbekannte Nummer)."
        )
    if status == 403:
        return _("Dafür fehlt dir die Berechtigung.")
    if status == 429:
        return _("Zu viele Anfragen. Bitte etwas später erneut.")
    if isinstance(body, dict):
        parts = []
        for key, value in body.items():
            text = " ".join(str(v) for v in value) if isinstance(value, list) else str(value)
            parts.append(text if key in ("detail", "non_field_errors") else f"{key}: {text}")
        if parts:
            return " · ".join(parts)
    if isinstance(body, list) and body:
        return " · ".join(str(v) for v in body)
    return _("Das hat nicht geklappt (Fehler {status}).").format(status=status)


def _dump(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1, default=str)


def _int(args: dict, name: str) -> int:
    value = args.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ToolError(_("„%(name)s“ muss eine Nummer sein.") % {"name": name})
    return value


def _str(args: dict, name: str, limit: int, required: bool = False) -> str | None:
    if name not in args:
        if required:
            raise ToolError(_("„%(name)s“ fehlt.") % {"name": name})
        return None
    value = args[name]
    if not isinstance(value, str):
        raise ToolError(_("„%(name)s“ muss ein Text sein.") % {"name": name})
    if len(value) > limit:
        raise ToolError(
            _("„%(name)s“ ist zu lang (höchstens %(limit)s Zeichen).")
            % {"name": name, "limit": limit}
        )
    if required and not value.strip():
        raise ToolError(_("„%(name)s“ fehlt.") % {"name": name})
    return value


def _views():
    from website import content_views, views

    return views, content_views


def _draft_hint() -> str:
    return _(
        "Gespeichert als Entwurf. Öffentlich wird es erst, wenn jemand es in HUBIplan "
        "veröffentlicht (Webseite › Texte bzw. Webseite › Startseite). Ansehen mit "
        "webseite_vorschau."
    )


# --- Werkzeuge ---


def _overview(args: dict, ctx: ClubContext) -> str:
    views, _c = _views()
    data = ctx.call(views.WebsiteView, "GET", "website/")
    site = data.get("website")
    if site is None:
        return _("Für diese Einheit ist noch keine Webseite eingerichtet.")
    labels = {**data.get("block_labels", {}), **data.get("home_labels", {})}
    summary = {
        "einheit": ctx.grant.organization.name,
        "zustand": site.get("effective_state"),
        "adresse": site.get("url"),
        "sprache": site.get("language"),
        "design": site.get("design"),
        "modul_an": data.get("module_enabled"),
        "darf_inhalte_bearbeiten": data.get("can_edit_content"),
        "entwurf_offen": sorted((site.get("draft") or {}).keys()),
        "menue": [
            {"schluessel": item.get("key"), "name": item.get("label")}
            for item in site.get("menu_items", [])
        ],
        "bausteine": {
            key: {"an": on, "name": str(labels.get(key, key))}
            for key, on in (site.get("blocks") or {}).items()
        },
    }
    return (
        _("Webseite der Einheit. Texte mit webseite_texte, Startseite mit startseite_ansehen.")
        + "\n\n"
        + _dump(summary)
    )


def _texts(args: dict, ctx: ClubContext) -> str:
    _v, content_views = _views()
    data = ctx.call(content_views.TextListView, "GET", "website/texts/")
    rows = [
        {
            "nummer": t["id"],
            "art": t["kind"],
            "titel": t["title"],
            "adresse": t["slug"],
            "veroeffentlicht": t["is_published"],
            "entwurf_geaendert": t["has_changes"],
            "im_menue": t["show_in_menu"],
            "untereinheit": t.get("department_name"),
        }
        for t in data.get("texts", [])
    ]
    return (
        _(
            "Texte der Webseite (art: greeting = Begrüßung der Startseite, page = Textseite, "
            "unit = Text einer Untereinheit, intro = Einleitung eines Bereichs). Den Inhalt "
            "liefert webseite_text_lesen mit der Nummer."
        )
        + "\n\n"
        + _dump(rows)
    )


def _image_summary(image: dict | None) -> dict | None:
    if not image:
        return None
    return {
        "nummer": image["id"],
        "schluessel": image.get("key"),
        "beschreibung": image.get("alt_text") or image.get("caption") or "",
    }


def _text_read(args: dict, ctx: ClubContext) -> str:
    _v, content_views = _views()
    pk = _int(args, "nummer")
    t = ctx.call(content_views.TextDetailView, "GET", f"website/texts/{pk}/", pk=pk)
    data = {
        "nummer": t["id"],
        "art": t["kind"],
        "titel": t["title"],
        "adresse": t["slug"],
        "veroeffentlicht": t["is_published"],
        "entwurf_geaendert": t["has_changes"],
        "text": t.get("body", ""),
        "bild": _image_summary(t.get("image_data")),
    }
    if t.get("gallery"):
        data["bilder"] = t["gallery"]
        data["bilder_takt"] = t.get("gallery_interval")
        data["bilder_zufall"] = t.get("gallery_random")
    if t.get("has_changes") and t.get("is_published"):
        data["veroeffentlichter_titel"] = t.get("published_title")
        data["veroeffentlichter_text"] = t.get("published_body")
    if t.get("kind") == "page" and not t.get("has_timeline"):
        # Abschnitte der Textseite (#78); „body“ ist der Text der Seite mit dem Bild oben
        data["abschnitte"] = list(t.get("sections") or [])
    return (
        _(
            "Text im Entwurf (Markdown; Bilder als ![Beschreibung](bild:Schlüssel), siehe "
            "webseite_bilder). Textseiten haben „abschnitte“ wie die Startseite; ändern mit "
            "textseite_aufbau_aendern und textseite_abschnitt_aendern."
        )
        + "\n\n"
        + _dump(data)
    )


def _image_args(args: dict, body: dict, *, carousel: bool) -> None:
    """Bild oben auf der Seite und Bilderkarussell wie in der Oberfläche (#415)."""
    if "bild" in args:
        value = args["bild"]
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 1
        ):
            raise ToolError(_("„bild“ muss eine Bildnummer oder null sein."))
        body["image"] = value
    if not carousel:
        return
    if "bilder" in args:
        value = args["bilder"]
        if not isinstance(value, list) or not all(
            isinstance(v, int) and not isinstance(v, bool) for v in value
        ):
            raise ToolError(_("„bilder“ muss eine Liste von Bildnummern sein."))
        body["gallery"] = value
    if "bilder_takt" in args:
        value = args["bilder_takt"]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ToolError(_("„bilder_takt“ muss eine Zahl (Sekunden) sein."))
        body["gallery_interval"] = value
    if "bilder_zufall" in args:
        if not isinstance(args["bilder_zufall"], bool):
            raise ToolError(_("„bilder_zufall“ muss wahr oder falsch sein."))
        body["gallery_random"] = args["bilder_zufall"]


def _alt_hint(ctx: ClubContext, ids: list[int]) -> str:
    """Hinweis auf gewählte Bilder ohne Alternativtext (wie in der Oberfläche)."""
    if not ids:
        return ""
    _v, content_views = _views()
    images = ctx.call(content_views.ImageListView, "GET", "website/images/") or []
    missing = [
        str(i["id"])
        for i in images
        if i["id"] in ids and not i.get("decorative") and not (i.get("alt_text") or "").strip()
    ]
    if not missing:
        return ""
    return " " + _(
        "Hinweis: Bild {numbers} hat noch keinen Alternativtext. Bitte mit bild_beschreiben "
        "ergänzen, damit die Seite auch vorgelesen verständlich ist."
    ).format(numbers=", ".join(missing))


def _chosen_images(body: dict) -> list[int]:
    ids = [body["image"]] if body.get("image") else []
    return ids + [v for v in body.get("gallery") or [] if v not in ids]


def _text_change(args: dict, ctx: ClubContext) -> str:
    _v, content_views = _views()
    pk = _int(args, "nummer")
    body = {}
    title = _str(args, "titel", MAX_TITLE)
    text = _str(args, "text", MAX_BODY)
    if title is not None:
        if not title.strip():
            raise ToolError(_("„titel“ darf nicht leer sein."))
        body["title"] = title.strip()
    if text is not None:
        body["body"] = text
    _image_args(args, body, carousel=True)
    if not body:
        raise ToolError(_("Bitte titel, text, bild oder bilder angeben."))
    t = ctx.call(content_views.TextDetailView, "PUT", f"website/texts/{pk}/", body, pk=pk)
    return (
        _("Text „{title}“ (Nummer {pk}) geändert.").format(title=t["title"], pk=t["id"])
        + " "
        + _draft_hint()
        + _alt_hint(ctx, _chosen_images(body))
    )


def _page_create(args: dict, ctx: ClubContext) -> str:
    _v, content_views = _views()
    title = _str(args, "titel", MAX_TITLE, required=True).strip()
    slug = _str(args, "adresse", 80, required=True).strip()
    text = _str(args, "text", MAX_BODY) or ""
    body = {"kind": "page", "title": title, "slug": slug, "body": text}
    _image_args(args, body, carousel=False)
    t = ctx.call(content_views.TextListView, "POST", "website/texts/", body)
    return (
        _("Textseite „{title}“ angelegt (Nummer {pk}, Adresse {slug}).").format(
            title=t["title"], pk=t["id"], slug=t["slug"]
        )
        + " "
        + _draft_hint()
        + _alt_hint(ctx, _chosen_images(body))
    )


def _home_sections(data: dict) -> list[dict]:
    site = data.get("website") or {}
    draft = site.get("draft") or {}
    return draft.get("home_sections") or site.get("home_sections") or []


def _home_read(args: dict, ctx: ClubContext) -> str:
    views, _c = _views()
    data = ctx.call(views.WebsiteView, "GET", "website/")
    if data.get("website") is None:
        return _("Für diese Einheit ist noch keine Webseite eingerichtet.")
    labels = data.get("home_labels", {})
    kinds = data.get("home_kinds", {})
    hints = data.get("home_kind_hints", {})
    rows = []
    for s in _home_sections(data):
        row = {"schluessel": s.get("key"), "an": s.get("on")}
        if "kind" in s:
            row["art"] = s["kind"]
            row["name"] = str(kinds.get(s["kind"], s["kind"]))
            row["hinweis"] = str(hints.get(s["kind"], ""))
            row["inhalt"] = s.get("data") or {}
        else:
            row["name"] = str(labels.get(s.get("key"), s.get("key")))
            row["fester_bereich"] = True
        rows.append(row)
    return (
        _(
            "Abschnitte der Startseite im Entwurf, in Reihenfolge. Feste Bereiche füllt HUBIplan "
            "selbst. Eigene Abschnitte (mit „art“) ändert startseite_abschnitt_aendern; "
            "Reihenfolge, An/Aus und Aussehen bleiben der Webseitenverwaltung in HUBIplan."
        )
        + "\n\n"
        + _dump(rows)
    )


def _home_change(args: dict, ctx: ClubContext) -> str:
    views, _c = _views()
    key = _str(args, "schluessel", 40, required=True)
    content = args.get("inhalt")
    if not isinstance(content, dict) or not content:
        raise ToolError(_("„inhalt“ muss ein Objekt mit den geänderten Feldern sein."))
    data = ctx.call(views.WebsiteView, "GET", "website/")
    if data.get("website") is None:
        raise ToolError(_("Für diese Einheit ist noch keine Webseite eingerichtet."))
    sections = [dict(s) for s in _home_sections(data)]
    target = next((s for s in sections if s.get("key") == key), None)
    if target is None:
        raise ToolError(_("Diesen Abschnitt gibt es nicht. Erst startseite_ansehen aufrufen."))
    if "kind" not in target:
        raise ToolError(_("Feste Bereiche füllt HUBIplan selbst; sie haben keinen Inhalt."))
    target["data"] = {**(target.get("data") or {}), **content}
    ctx.call(views.HomeContentView, "PUT", "website/home-content/", {"home_sections": sections})
    return _("Abschnitt {key} der Startseite geändert.").format(key=key) + " " + _draft_hint()


def _images(args: dict, ctx: ClubContext) -> str:
    _v, content_views = _views()
    data = ctx.call(content_views.ImageListView, "GET", "website/images/")
    rows = [
        {
            "nummer": i["id"],
            "schluessel": i["key"],
            "beschreibung": i.get("alt_text") or i.get("caption"),
            "markdown": i.get("markdown"),
            "breite": i.get("width"),
            "hoehe": i.get("height"),
        }
        for i in data or []
    ]
    return (
        _(
            "Bilder der Webseite. In Texten mit der Markdown-Zeile einbinden. Neue Bilder: "
            "bild_hochladen_vorbereiten liefert einen Link zum Hochladen."
        )
        + "\n\n"
        + _dump(rows)
    )


def _preview(args: dict, ctx: ClubContext) -> str:
    views, _c = _views()
    data = ctx.call(views.PreviewOpenView, "POST", "website/preview/")
    if not data.get("url"):
        return _(
            "Die Webseite hat noch keine Adresse. Die Vorschau gibt es in HUBIplan unter Webseite."
        )
    return _("Vorschau mit allen Entwürfen (kurz gültig, nur zum Ansehen): {url}").format(
        url=data.get("url")
    )


def _check(args: dict, ctx: ClubContext) -> str:
    views, content_views = _views()
    data = ctx.call(views.WebsiteView, "GET", "website/")
    site = data.get("website")
    if site is None:
        return _("Für diese Einheit ist noch keine Webseite eingerichtet.")
    texts = ctx.call(content_views.TextListView, "GET", "website/texts/").get("texts", [])
    result = {
        "pruefpunkte": [
            {"name": c.get("label"), "ok": c.get("ok"), "hinweis": c.get("hint")}
            for c in site.get("checks", [])
        ],
        "texte_mit_entwurf": [
            {"nummer": t["id"], "titel": t["title"]} for t in texts if t.get("has_changes")
        ],
        "gestaltung_im_entwurf": sorted((site.get("draft") or {}).keys()),
    }
    return (
        _("Prüfpunkte der Webseite und offene Entwürfe. Veröffentlichen geht nur in HUBIplan.")
        + "\n\n"
        + _dump(result)
    )


NUMBER = {"type": "integer", "minimum": 1, "description": gettext_lazy("Nummer des Textes.")}
IMAGE_OR_NULL = {
    "type": ["integer", "null"],
    "minimum": 1,
    "description": gettext_lazy(
        "Bildnummer aus webseite_bilder für das Bild oben auf der Seite; null entfernt es."
    ),
}


def _schema(props: dict | None = None, required: list | None = None) -> dict:
    schema = {
        "type": "object",
        "properties": {**(props or {}), "sprache": LANG_SCHEMA},
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


CLUB_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="webseite_ansehen",
        title=gettext_lazy("Webseite ansehen"),
        description=gettext_lazy(
            "Überblick über die Webseite der verbundenen Einheit: Zustand, Adresse, Menü, "
            "Bausteine und ob ein Entwurf offen ist."
        ),
        schema=_schema(),
        run=_overview,
        scope=SCOPE_READ,
    ),
    Tool(
        name="webseite_texte",
        title=gettext_lazy("Texte der Webseite"),
        description=gettext_lazy(
            "Listet alle Texte der Webseite (Begrüßung, Textseiten, Texte der Untereinheiten, "
            "Einleitungen) mit Nummer, Titel und Stand."
        ),
        schema=_schema(),
        run=_texts,
        scope=SCOPE_READ,
    ),
    Tool(
        name="webseite_text_lesen",
        title=gettext_lazy("Text lesen"),
        description=gettext_lazy(
            "Liefert Titel, Inhalt (Markdown) und Bild eines Textes im Entwurf, dazu den "
            "veröffentlichten Stand, wenn er abweicht."
        ),
        schema=_schema({"nummer": NUMBER}, ["nummer"]),
        run=_text_read,
        scope=SCOPE_READ,
    ),
    Tool(
        name="webseite_bilder",
        title=gettext_lazy("Bilder der Webseite"),
        description=gettext_lazy(
            "Listet die Bilder der Webseite mit der Markdown-Zeile zum Einbinden in Texte."
        ),
        schema=_schema(),
        run=_images,
        scope=SCOPE_READ,
    ),
    Tool(
        name="startseite_ansehen",
        title=gettext_lazy("Startseite ansehen"),
        description=gettext_lazy(
            "Abschnitte der Startseite im Entwurf, in Reihenfolge, mit Art und Inhalt."
        ),
        schema=_schema(),
        run=_home_read,
        scope=SCOPE_READ,
    ),
    Tool(
        name="webseite_pruefen",
        title=gettext_lazy("Webseite prüfen"),
        description=gettext_lazy(
            "Prüfpunkte der Webseite (z. B. Impressum, Datenschutzhinweise) und welche Texte "
            "und Gestaltung noch als Entwurf offen sind."
        ),
        schema=_schema(),
        run=_check,
        scope=SCOPE_READ,
    ),
    Tool(
        name="webseite_vorschau",
        title=gettext_lazy("Vorschau öffnen"),
        description=gettext_lazy(
            "Liefert einen kurz gültigen Link zur Vorschau der Webseite mit allen Entwürfen."
        ),
        schema=_schema(),
        run=_preview,
        scope=SCOPE_READ,
    ),
    Tool(
        name="webseite_text_aendern",
        title=gettext_lazy("Text ändern (Entwurf)"),
        description=gettext_lazy(
            "Ändert Titel, Inhalt (Markdown) und/oder Bild eines Textes im Entwurf. Den "
            "bisherigen Inhalt vorher mit webseite_text_lesen holen; „text“ ersetzt ihn ganz. "
            "„bild“ ist das Bild oben auf der Seite (bei der Begrüßung das große Titelbild der "
            "Startseite), „bilder“ das Bilderkarussell der Begrüßung. Bildnummern liefert "
            "webseite_bilder. Veröffentlicht wird nur in HUBIplan."
        ),
        schema=_schema(
            {
                "nummer": NUMBER,
                "titel": {"type": "string", "maxLength": MAX_TITLE},
                "text": {
                    "type": "string",
                    "maxLength": MAX_BODY,
                    "description": gettext_lazy("Neuer Inhalt in Markdown (ersetzt den alten)."),
                },
                "bild": IMAGE_OR_NULL,
                "bilder": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1},
                    "maxItems": 10,
                    "description": gettext_lazy(
                        "Bilderkarussell der Begrüßung oder einer Untereinheit: Bildnummern in "
                        "der Reihenfolge (ersetzt die alte Liste, leere Liste entfernt es)."
                    ),
                },
                "bilder_takt": {
                    "type": "integer",
                    "minimum": 3,
                    "maximum": 30,
                    "description": gettext_lazy("Sekunden bis zum nächsten Bild im Karussell."),
                },
                "bilder_zufall": {
                    "type": "boolean",
                    "description": gettext_lazy("Karussell mit einem zufälligen Bild beginnen."),
                },
            },
            ["nummer"],
        ),
        run=_text_change,
        writes=True,
        scope=SCOPE_DRAFT,
    ),
    Tool(
        name="webseite_textseite_anlegen",
        title=gettext_lazy("Textseite anlegen (Entwurf)"),
        description=gettext_lazy(
            "Legt eine neue Textseite an, auf Wunsch mit Bild oben auf der Seite. Sie bleibt "
            "unveröffentlicht, bis jemand sie in HUBIplan veröffentlicht."
        ),
        schema=_schema(
            {
                "titel": {"type": "string", "maxLength": MAX_TITLE},
                "adresse": {
                    "type": "string",
                    "maxLength": 80,
                    "description": gettext_lazy(
                        "Adresse der Seite, nur Kleinbuchstaben, Ziffern und Bindestriche, "
                        "z. B. ueber-uns."
                    ),
                },
                "text": {"type": "string", "maxLength": MAX_BODY},
                "bild": IMAGE_OR_NULL,
            },
            ["titel", "adresse"],
        ),
        run=_page_create,
        writes=True,
        scope=SCOPE_DRAFT,
    ),
    Tool(
        name="startseite_abschnitt_aendern",
        title=gettext_lazy("Abschnitt der Startseite ändern (Entwurf)"),
        description=gettext_lazy(
            "Ändert den Inhalt eines eigenen Abschnitts der Startseite im Entwurf. "
            "„inhalt“ enthält nur die geänderten Felder, aufgebaut wie „inhalt“ aus "
            "startseite_ansehen. Reihenfolge, An/Aus und Aussehen ändert es nicht."
        ),
        schema=_schema(
            {
                "schluessel": {
                    "type": "string",
                    "maxLength": 40,
                    "description": gettext_lazy("Schlüssel des Abschnitts, z. B. c:ab12."),
                },
                "inhalt": {"type": "object"},
            },
            ["schluessel", "inhalt"],
        ),
        run=_home_change,
        writes=True,
        scope=SCOPE_DRAFT,
    ),
)


def tools_for(ctx: Context):
    """Hilfe immer; Webseite je nach Bereich der Zustimmung."""
    from .club_design import DESIGN_TOOLS
    from .club_theme import THEME_TOOLS

    scopes = set(getattr(getattr(ctx, "grant", None), "scopes", None) or [])
    club = (*CLUB_TOOLS, *DESIGN_TOOLS, *THEME_TOOLS)
    return (*TOOLS, *(t for t in club if t.scope in scopes))
