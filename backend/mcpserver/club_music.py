"""Musik über die KI-Schnittstelle: Auftritte, Uniformen und Auftrittsarten (Issues #712/#713).

Eigener Bereich ``musik.auftritte`` (nur mit eigenem Haken beim Verbinden), weil Änderungen
sofort gelten. Die Werkzeuge rufen dieselben Ansichten wie Musik in HUBIplan auf (Rechte
„Musik ansehen/bearbeiten“, Prüfungen, Änderungsprotokoll). Vertrag, Gage und Abrechnung gibt
es hier bewusst nicht.
"""

from __future__ import annotations

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from .club import ClubContext, _dump, _schema
from .oauth import SCOPE_MUSIC
from .tools import Tool, ToolError

MAX_ROWS = 300
FORMATIONS = ["seated", "standing", "march"]
LIST = {"get": "list"}
CREATE = {"post": "create"}
UPDATE = {"patch": "partial_update"}


def _views():
    from music import masterdata, views

    return views, masterdata


def _number(args: dict, name: str, nullable: bool = False):
    value = args.get(name)
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ToolError(_("„%(name)s“ muss eine Nummer sein.") % {"name": name})
    return value


def _text(args: dict, name: str, limit: int) -> str:
    value = args.get(name)
    if not isinstance(value, str) or len(value) > limit:
        raise ToolError(
            _("„%(name)s“ muss ein Text mit höchstens %(limit)s Zeichen sein.")
            % {"name": name, "limit": limit}
        )
    return value


def _read(args: dict, ctx: ClubContext) -> str:
    views, masterdata = _views()
    uniforms = ctx.call(masterdata.UniformViewSet, "GET", "music/uniforms/", actions=LIST)
    kinds = ctx.call(
        masterdata.PerformanceKindViewSet, "GET", "music/performance-kinds/", actions=LIST
    )
    performances = ctx.call(views.PerformanceViewSet, "GET", "music/performances/", actions=LIST)
    performances = sorted(performances, key=lambda p: str(p.get("starts_at") or ""))
    return _dump(
        {
            "hinweis": _(
                "Uniformen und Auftrittsarten gelten für die ganze Einheit. Ein Auftritt mit "
                "„hauptauftritt“ ist ein weiterer Tag eines Festes: Vertrag und Gage führt der "
                "Hauptauftritt. Spielform: seated (sitzend), standing (stehend), march (Umzug)."
            ),
            "uniformen": [
                {
                    "nummer": u["id"],
                    "name": u["name"],
                    "beschreibung": u["description"],
                    "checkliste": u["checklist"],
                    "bild": u["has_image"],
                    "aktiv": u["active"],
                }
                for u in uniforms
            ],
            "auftrittsarten": [
                {
                    "nummer": k["id"],
                    "name": k["name"],
                    "spielform": k["formation"] or None,
                    "uniform": k["uniform"],
                    "auf_webseite": k["on_website"],
                    "aktiv": k["active"],
                }
                for k in kinds
            ],
            "auftritte": [
                {
                    "nummer": p["id"],
                    "titel": p["title"],
                    "beginn": p["starts_at"],
                    "ort": p["location"],
                    "abgesagt": p["cancelled"],
                    "art": p["kind"],
                    "uniform": p["uniform_choice"],
                    "uniform_ergaenzung": p["uniform"],
                    "spielform": p["formation"],
                    "hauptauftritt": p["main"],
                    "weitere_tage": p["days"],
                    "veranstaltung": p["project"],
                }
                for p in performances[:MAX_ROWS]
            ],
            "auftritte_gesamt": len(performances),
        }
    )


def _save(ctx: ClubContext, view, path: str, args: dict, data: dict) -> dict:
    if "nummer" in args:
        pk = _number(args, "nummer")
        return ctx.call(view, "PATCH", f"{path}{pk}/", data, actions=UPDATE, pk=pk)
    if not data.get("name"):
        raise ToolError(_("„%(name)s“ fehlt.") % {"name": "name"})
    return ctx.call(view, "POST", path, data, actions=CREATE)


def _uniform(args: dict, ctx: ClubContext) -> str:
    _views_, masterdata = _views()
    data = {}
    for key, field, limit in (("name", "name", 100), ("beschreibung", "description", 1000)):
        if key in args:
            data[field] = _text(args, key, limit)
    if "checkliste" in args:
        items = args["checkliste"]
        if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
            raise ToolError(_("„checkliste“ muss eine Liste von Texten sein."))
        data["checklist"] = items
    if "aktiv" in args:
        data["active"] = bool(args["aktiv"])
    row = _save(ctx, masterdata.UniformViewSet, "music/uniforms/", args, data)
    return _("Uniform „%(name)s“ gespeichert (Nummer %(id)s).") % {
        "name": row["name"],
        "id": row["id"],
    }


def _kind(args: dict, ctx: ClubContext) -> str:
    _views_, masterdata = _views()
    data = {}
    if "name" in args:
        data["name"] = _text(args, "name", 100)
    if "spielform" in args:
        value = args["spielform"]
        if value not in [*FORMATIONS, None, ""]:
            raise ToolError(_("„spielform“: seated, standing, march oder leer."))
        data["formation"] = value or ""
    if "uniform" in args:
        data["uniform"] = _number(args, "uniform", nullable=True)
    if "auf_webseite" in args:
        data["on_website"] = bool(args["auf_webseite"])
    if "aktiv" in args:
        data["active"] = bool(args["aktiv"])
    row = _save(ctx, masterdata.PerformanceKindViewSet, "music/performance-kinds/", args, data)
    return _("Auftrittsart „%(name)s“ gespeichert (Nummer %(id)s).") % {
        "name": row["name"],
        "id": row["id"],
    }


def _performance(args: dict, ctx: ClubContext) -> str:
    views, _masterdata = _views()
    pk = _number(args, "nummer")
    data = {}
    for key, field in (("art", "kind"), ("uniform", "uniform_choice"), ("hauptauftritt", "main")):
        if key in args:
            data[field] = _number(args, key, nullable=True)
    if "uniform_ergaenzung" in args:
        data["uniform"] = _text(args, "uniform_ergaenzung", 300)
    if "spielform" in args:
        if args["spielform"] not in FORMATIONS:
            raise ToolError(_("„spielform“: seated, standing oder march."))
        data["formation"] = args["spielform"]
    if not data:
        raise ToolError(_("Bitte mindestens eine Angabe zum Ändern nennen."))
    row = ctx.call(
        views.PerformanceViewSet,
        "PATCH",
        f"music/performances/{pk}/",
        data,
        actions=UPDATE,
        pk=pk,
    )
    return _dump(
        {
            "gespeichert": row["title"],
            "art": row["kind_name"],
            "uniform": row["uniform_text"],
            "hauptauftritt": row["main"],
        }
    )


NUMBER_OR_NULL = {"type": ["integer", "null"], "minimum": 1}

MUSIC_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="musik_ansehen",
        title=gettext_lazy("Musik: Auftritte, Uniformen und Auftrittsarten ansehen"),
        description=gettext_lazy(
            "Liste der Uniformen (mit Checkliste), der Auftrittsarten und der Auftritte mit "
            "Art, Uniform, Spielform und Hauptauftritt (mehrtägige Feste). Braucht das Recht, "
            "Musik und Termine anzusehen."
        ),
        schema=_schema(),
        run=_read,
        scope=SCOPE_MUSIC,
    ),
    Tool(
        name="musik_uniform_speichern",
        title=gettext_lazy("Musik: Uniform anlegen oder ändern (wirkt sofort)"),
        description=gettext_lazy(
            "Ohne „nummer“ neue Uniform anlegen, mit „nummer“ ändern. „checkliste“ ersetzt die "
            "ganze Liste dessen, was dazugehört (höchstens 30 Punkte). Bilder lädt eine Person "
            "in HUBIplan hoch."
        ),
        schema=_schema(
            {
                "nummer": {"type": "integer", "minimum": 1},
                "name": {"type": "string", "maxLength": 100},
                "beschreibung": {"type": "string", "maxLength": 1000},
                "checkliste": {
                    "type": "array",
                    "maxItems": 30,
                    "items": {"type": "string", "maxLength": 200},
                },
                "aktiv": {"type": "boolean"},
            }
        ),
        run=_uniform,
        writes=True,
        scope=SCOPE_MUSIC,
    ),
    Tool(
        name="musik_auftrittsart_speichern",
        title=gettext_lazy("Musik: Auftrittsart anlegen oder ändern (wirkt sofort)"),
        description=gettext_lazy(
            "Ohne „nummer“ neue Auftrittsart anlegen, mit „nummer“ ändern. Spielform und "
            "Uniform sind Vorschläge beim Wählen der Art. „auf_webseite“: Art beim Termin auf "
            "der Vereinswebseite nennen."
        ),
        schema=_schema(
            {
                "nummer": {"type": "integer", "minimum": 1},
                "name": {"type": "string", "maxLength": 100},
                "spielform": {"type": ["string", "null"], "enum": [*FORMATIONS, "", None]},
                "uniform": NUMBER_OR_NULL,
                "auf_webseite": {"type": "boolean"},
                "aktiv": {"type": "boolean"},
            }
        ),
        run=_kind,
        writes=True,
        scope=SCOPE_MUSIC,
    ),
    Tool(
        name="musik_auftritt_aendern",
        title=gettext_lazy("Musik: Art, Uniform oder Hauptauftritt eines Auftritts setzen"),
        description=gettext_lazy(
            "Setzt bei einem Auftritt Art, Uniform (Nummer aus musik_ansehen, null entfernt), "
            "Ergänzung zur Uniform, Spielform oder den Hauptauftritt (weiterer Tag eines Festes, "
            "null löst ihn). Wirkt sofort. Nicht möglich, solange eine Zusage des Auftraggebers "
            "besteht."
        ),
        schema=_schema(
            {
                "nummer": {"type": "integer", "minimum": 1},
                "art": NUMBER_OR_NULL,
                "uniform": NUMBER_OR_NULL,
                "uniform_ergaenzung": {"type": "string", "maxLength": 300},
                "spielform": {"type": "string", "enum": FORMATIONS},
                "hauptauftritt": NUMBER_OR_NULL,
            },
            ["nummer"],
        ),
        run=_performance,
        writes=True,
        scope=SCOPE_MUSIC,
    ),
)
