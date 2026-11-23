"""Eigene Beiträge unter „Aktuelles“ über die KI-Schnittstelle (Issue #707).

Wie bei den Textseiten landet alles im Entwurf; veröffentlicht wird nur in HUBIplan unter
Webseite › Aktuelles. Die Werkzeuge rufen dieselben Ansichten wie die Oberfläche auf
(Recht „Inhalte bearbeiten“, Prüfungen, Änderungsprotokoll).
"""

from __future__ import annotations

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from .club import ClubContext, _dump, _int, _schema, _str
from .oauth import SCOPE_DRAFT, SCOPE_READ
from .tools import Tool, ToolError

NUMBER = {"type": "integer", "minimum": 1}
VIDEO = {
    "type": "object",
    "properties": {
        "adresse": {"type": "string", "maxLength": 500},
        "titel": {"type": "string", "maxLength": 120},
        "bild": {**NUMBER, "description": gettext_lazy("Vorschaubild (Bildnummer)")},
    },
    "required": ["adresse"],
    "additionalProperties": False,
}


def _views():
    from website import news_views

    return news_views


def _row(p: dict, full: bool = False) -> dict:
    row = {
        "nummer": p["id"],
        "titel": p["title"],
        "datum": p["date"],
        "adresse": p["slug"],
        "untereinheit": p["department_name"],
        "veroeffentlicht": p["is_published"],
        "entwurf_geaendert": p["is_published"] and p["has_changes"],
        "bilder": p["images"],
        "videos": [
            {"adresse": v["url"], "titel": v.get("title", ""), "bild": v.get("image")}
            for v in p["videos"]
        ],
    }
    if full:
        row["text"] = p["body"]
    return row


def _read(args: dict, ctx: ClubContext) -> str:
    views = _views()
    if "nummer" in args:
        pk = _int(args, "nummer")
        data = ctx.call(views.NewsDetailView, "GET", f"website/news/{pk}/", pk=pk)
        return _dump(_row(data, full=True))
    data = ctx.call(views.NewsListView, "GET", "website/news/")
    return (
        _(
            "Eigene Beiträge unter „Aktuelles“, neueste zuerst (ohne Text; den Text zeigt "
            "beitraege_ansehen mit „nummer“). Die Webseite mischt sie nach Datum mit den "
            "Beiträgen aus Instagram und Facebook. Untereinheiten: {units}"
        ).format(units=_dump(data.get("units", [])))
        + "\n\n"
        + _dump([_row(p) for p in data.get("posts", [])])
    )


def _save(args: dict, ctx: ClubContext) -> str:
    views = _views()
    payload: dict = {}
    for name, field, limit in (
        ("titel", "title", 120),
        ("datum", "date", 10),
        ("text", "body", 20_000),
        ("adresse", "slug", 80),
    ):
        value = _str(args, name, limit)
        if value is not None:
            payload[field] = value
    if "bilder" in args:
        images = args["bilder"]
        if not isinstance(images, list) or not all(
            isinstance(i, int) and not isinstance(i, bool) for i in images
        ):
            raise ToolError(_("„bilder“ ist eine Liste von Bildnummern."))
        payload["images"] = images
    if "videos" in args:
        videos = args["videos"]
        if not isinstance(videos, list) or not all(isinstance(v, dict) for v in videos):
            raise ToolError(_("„videos“ ist eine Liste mit „adresse“, „titel“ und „bild“."))
        payload["videos"] = [
            {"url": v.get("adresse"), "title": v.get("titel") or "", "image": v.get("bild")}
            for v in videos
        ]
    if "untereinheit" in args:
        unit = args["untereinheit"]
        if unit is not None and (isinstance(unit, bool) or not isinstance(unit, int)):
            raise ToolError(_("„untereinheit“ muss eine Nummer sein (oder null)."))
        payload["department"] = unit
    if "nummer" in args:
        pk = _int(args, "nummer")
        if not payload:
            raise ToolError(_("Nichts zu ändern."))
        data = ctx.call(views.NewsDetailView, "PUT", f"website/news/{pk}/", payload, pk=pk)
        message = _("Entwurf von Beitrag {pk} geändert.").format(pk=pk)
    else:
        if not payload.get("title"):
            raise ToolError(_("„titel“ fehlt."))
        if not payload.get("date"):
            raise ToolError(_("„datum“ fehlt (JJJJ-MM-TT)."))
        data = ctx.call(views.NewsListView, "POST", "website/news/", payload)
        message = _("Beitrag {pk} als Entwurf angelegt.").format(pk=data["id"])
    return (
        message
        + " "
        + _(
            "Sichtbar wird er erst, wenn jemand ihn in HUBIplan unter Webseite › Aktuelles "
            "veröffentlicht. In der Vorschau (webseite_vorschau) ist der Entwurf schon zu sehen."
        )
        + "\n\n"
        + _dump(_row(data, full=True))
    )


def _delete(args: dict, ctx: ClubContext) -> str:
    views = _views()
    pk = _int(args, "nummer")
    data = ctx.call(views.NewsDetailView, "GET", f"website/news/{pk}/", pk=pk)
    if data["is_published"]:
        raise ToolError(
            _("Veröffentlichte Beiträge löscht nur ein Mensch in HUBIplan (Webseite › Aktuelles).")
        )
    ctx.call(views.NewsDetailView, "DELETE", f"website/news/{pk}/", pk=pk)
    return _("Entwurf {pk} gelöscht.").format(pk=pk)


NEWS_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="beitraege_ansehen",
        title=gettext_lazy("Eigene Beiträge ansehen"),
        description=gettext_lazy(
            "Listet die eigenen Beiträge unter „Aktuelles“ (Titel, Datum, Stand, Bilder, "
            "Videos). Mit „nummer“ ein Beitrag samt Text (Markdown)."
        ),
        schema=_schema({"nummer": NUMBER}),
        run=_read,
        scope=SCOPE_READ,
    ),
    Tool(
        name="beitrag_speichern",
        title=gettext_lazy("Eigenen Beitrag speichern"),
        description=gettext_lazy(
            "Legt ohne „nummer“ einen eigenen Beitrag unter „Aktuelles“ als Entwurf an "
            "(„titel“ und „datum“ Pflicht, Datum auch rückwirkend, z. B. für alte Beiträge "
            "einer früheren Webseite), mit „nummer“ ändert es den Entwurf; nur angegebene Felder "
            "ändern sich. „text“ ist Markdown, Bilder darin als ![Text](bild:<key>) aus "
            "bilder_suchen. „bilder“ (Bildnummern) erscheinen unter dem Text, „videos“ als "
            "Vorschaubild mit Link (nie eingebettet). Veröffentlicht wird nur in HUBIplan."
        ),
        schema=_schema(
            {
                "nummer": NUMBER,
                "titel": {"type": "string", "maxLength": 120},
                "datum": {
                    "type": "string",
                    "maxLength": 10,
                    "description": gettext_lazy("JJJJ-MM-TT"),
                },
                "text": {"type": "string", "maxLength": 20_000},
                "bilder": {"type": "array", "items": NUMBER, "maxItems": 20},
                "videos": {"type": "array", "items": VIDEO, "maxItems": 6},
                "adresse": {
                    "type": "string",
                    "maxLength": 80,
                    "description": gettext_lazy(
                        "Teil der Adresse auf der Webseite, z. B. sommerfest-2019; ohne Angabe "
                        "aus dem Titel"
                    ),
                },
                "untereinheit": {
                    "type": ["integer", "null"],
                    "description": gettext_lazy(
                        "Nummer einer Untereinheit (Beitrag erscheint auf ihrer Seite), null = "
                        "Beitrag der Einheit"
                    ),
                },
            }
        ),
        run=_save,
        writes=True,
        scope=SCOPE_DRAFT,
    ),
    Tool(
        name="beitrag_loeschen",
        title=gettext_lazy("Beitragsentwurf löschen"),
        description=gettext_lazy(
            "Löscht einen eigenen Beitrag, der noch nie veröffentlicht wurde. Veröffentlichte "
            "Beiträge löscht nur ein Mensch in HUBIplan."
        ),
        schema=_schema({"nummer": NUMBER}, ["nummer"]),
        run=_delete,
        writes=True,
        destructive=True,
        scope=SCOPE_DRAFT,
    ),
)
