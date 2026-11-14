"""Briefbogen der Einheit über die KI-Schnittstelle (Issue #470, docs/mcp.md).

Der Briefbogen gilt für die Word-Vorlage und alle PDF-Briefe (Rechnung, Storno, Mahnung,
Spendenquittung, Rundschreiben). Er hat keinen Entwurf: Änderungen gelten sofort. Die
Werkzeuge rufen dieselben Ansichten wie Einstellungen › Briefbogen auf (Recht, die Einheit
zu bearbeiten, Prüfung der Werte, Änderungsprotokoll).
"""

from __future__ import annotations

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from .club import ClubContext, _dump, _schema
from .oauth import SCOPE_LETTERHEAD, SCOPE_READ
from .tools import Tool, ToolError

OFFICE_FONTS = ["Arial", "Calibri", "Cambria", "Georgia", "Times New Roman", "Verdana"]
WEB_FONTS = [
    "Source Sans 3",
    "Crimson Pro",
    "Atkinson Hyperlegible",
    "Open Sans",
    "Roboto",
    "Oswald",
    "UnifrakturMaguntia",
]
SLOTS = ["0", "1", "2", "3", "4", "5"]

# Name im Werkzeug → Feld der Schnittstelle
FIELDS = {
    "briefbogen": "mode",
    "aufbau": "form",
    "logo": "logo_position",
    "logo_groesse": "logo_size",
    "name_neben_logo": "show_name",
    "zusatzzeile": "tagline",
    "schrift": "font",
    "schrift_ueberschriften": "heading_font",
    "ersatzschrift": "font_fallback",
    "ersatzschrift_ueberschriften": "heading_font_fallback",
    "linienfarbe": "line_color",
    "linie_kopf": "head_line",
    "linie_fusszeile": "footer_line",
    "titelfarbe": "title_color",
    "tabellenlinien": "table_line_color",
    "tabellenstreifen": "table_stripe",
    "anrede": "salutation",
    "grussformel": "closing",
}
FOOTER = {
    "bankverbindung": "show_bank",
    "telefon": "show_phone",
    "email": "show_email",
    "webseite": "show_website",
    "vorstand": "show_board",
    "register": "show_register",
    "social_media": "show_social",
}
SLOT_FIELDS = {"line_color", "table_line_color"}


def _views():
    from letterhead import views

    return views


def _path(args: dict) -> tuple[str, dict]:
    unit = args.get("untereinheit")
    if unit is None:
        return "letterhead/", {}
    if isinstance(unit, bool) or not isinstance(unit, int) or unit < 1:
        raise ToolError(_("„%(name)s“ muss eine Nummer sein.") % {"name": "untereinheit"})
    return f"letterhead/units/{unit}/", {"unit_id": unit}


def _view(args: dict):
    views = _views()
    return views.UnitLetterheadView if args.get("untereinheit") else views.OrgLetterheadView


def _summary(data: dict) -> dict:
    lh = data.get("letterhead") or {}
    result = {key: lh.get(field) for key, field in FIELDS.items()}
    for key in ("linienfarbe", "tabellenlinien"):
        if result.get(key) is not None:
            result[key] = int(result[key])
    result["fusszeile"] = {key: lh.get(field) for key, field in FOOTER.items()}
    return {
        "einheit": (data.get("organization") or {}).get("name"),
        "gilt_von": None
        if (data.get("owner") or {}).get("is_self")
        else (data.get("owner") or {}).get("name"),
        "einstellungen": result,
        "palette": [
            {"platz": p["slot"], "farbe": p["color"], "kontrast_auf_weiss": p["contrast"]}
            for p in data.get("palette") or []
        ],
        "hinweise": data.get("hints") or [],
    }


def _read(args: dict, ctx: ClubContext) -> str:
    path, kwargs = _path(args)
    data = ctx.call(_view(args), "GET", path, **kwargs)
    hint = _(
        "Briefbogen der Einheit (Word-Vorlage und alle PDF-Briefe). Farben sind Plätze der "
        "Palette: 0 Hauptfarbe, 1 Zweitfarbe, 2–5 weitere. Linien sollten auf Weiß einen "
        "Kontrast von mindestens 3:1 haben. „schrift_ueberschriften“ leer heißt wie der Text."
    )
    return hint + "\n\n" + _dump(_summary(data))


def _change(args: dict, ctx: ClubContext) -> str:
    body: dict = {}
    for key, field in FIELDS.items():
        if key not in args or args[key] is None:
            continue
        value = args[key]
        if field in SLOT_FIELDS or (field == "table_stripe" and isinstance(value, int)):
            if isinstance(value, bool) or not isinstance(value, int | str):
                raise ToolError(_("„%(name)s“ muss ein Palettenplatz sein.") % {"name": key})
            value = str(value)
        body[field] = value
    footer = args.get("fusszeile")
    if footer is not None:
        if not isinstance(footer, dict):
            raise ToolError(_("„%(name)s“ muss ein Objekt sein.") % {"name": "fusszeile"})
        for key, field in FOOTER.items():
            if footer.get(key) is not None:
                if not isinstance(footer[key], bool):
                    raise ToolError(_("„%(name)s“ ist ja oder nein.") % {"name": key})
                body[field] = footer[key]
    if not body:
        raise ToolError(_("Bitte angeben, was sich am Briefbogen ändern soll."))
    path, kwargs = _path(args)
    data = ctx.call(_view(args), "PATCH", path, body, **kwargs)
    return (
        _(
            "Briefbogen geändert ({keys}). Er gilt ab sofort für neue Briefe, Rechnungen und die "
            "Word-Vorlage; die Vorschau steht unter Einstellungen › Briefbogen."
        ).format(keys=", ".join(sorted(body)))
        + "\n\n"
        + _dump(_summary(data))
    )


UNIT = {
    "type": "integer",
    "minimum": 1,
    "description": gettext_lazy("Nummer einer Untereinheit; leer: die Einheit selbst."),
}
SLOT = {"type": "integer", "minimum": 0, "maximum": 5}
FONT = {"type": "string", "enum": [*OFFICE_FONTS, *WEB_FONTS]}

LETTERHEAD_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="briefbogen_ansehen",
        title=gettext_lazy("Briefbogen ansehen"),
        description=gettext_lazy(
            "Einstellungen des Briefbogens (Einstellungen › Briefbogen): Aufbau, Logo, Schriften, "
            "Linien- und Tabellenfarben, Fußzeile, dazu die Palette mit Kontrast und Hinweise."
        ),
        schema=_schema({"untereinheit": UNIT}),
        run=_read,
        scope=SCOPE_READ,
    ),
    Tool(
        name="briefbogen_aendern",
        title=gettext_lazy("Briefbogen ändern"),
        description=gettext_lazy(
            "Ändert den Briefbogen für Word-Vorlage und PDF-Briefe (Rechnungen, Mahnungen, "
            "Spendenquittungen, Rundschreiben). Gilt SOFORT, es gibt keinen Entwurf: vorher die "
            "Person fragen. Nur angegebene Werte ändern sich. Braucht das Recht, die Einheit zu "
            "bearbeiten."
        ),
        schema=_schema(
            {
                "untereinheit": UNIT,
                "briefbogen": {
                    "type": "string",
                    "enum": ["own", "inherit"],
                    "description": gettext_lazy(
                        "Nur Untereinheiten: eigener oder übernommener Briefbogen."
                    ),
                },
                "aufbau": {
                    "type": "string",
                    "enum": ["a", "b"],
                    "description": gettext_lazy("DIN 5008 Form A oder B."),
                },
                "logo": {"type": "string", "enum": ["right", "left", "none"]},
                "logo_groesse": {"type": "string", "enum": ["small", "medium", "large"]},
                "name_neben_logo": {
                    "type": "boolean",
                    "description": gettext_lazy(
                        "Aus, wenn das Logo den Namen schon enthält (Bildmarke mit Schriftzug)."
                    ),
                },
                "zusatzzeile": {"type": "string", "maxLength": 150},
                "schrift": FONT,
                "schrift_ueberschriften": {
                    "type": "string",
                    "enum": ["", *OFFICE_FONTS, *WEB_FONTS],
                    "description": gettext_lazy("Leer: wie der Text."),
                },
                "ersatzschrift": {
                    "type": "string",
                    "enum": OFFICE_FONTS,
                    "description": gettext_lazy(
                        "Ersatz in Word, wenn die Schrift der Webseite nicht installiert ist."
                    ),
                },
                "ersatzschrift_ueberschriften": {"type": "string", "enum": OFFICE_FONTS},
                "linienfarbe": SLOT,
                "linie_kopf": {"type": "boolean"},
                "linie_fusszeile": {"type": "boolean"},
                "titelfarbe": {"type": "string", "enum": ["black", "primary"]},
                "tabellenlinien": SLOT,
                "tabellenstreifen": {
                    "type": ["string", "integer"],
                    "description": gettext_lazy(
                        "„grey“ (hellgrau), „none“ (keine) oder ein Palettenplatz 0–5 (hell)."
                    ),
                },
                "anrede": {"type": "string", "maxLength": 100},
                "grussformel": {"type": "string", "maxLength": 100},
                "fusszeile": {
                    "type": "object",
                    "properties": {key: {"type": "boolean"} for key in FOOTER},
                    "additionalProperties": False,
                },
            }
        ),
        run=_change,
        writes=True,
        scope=SCOPE_LETTERHEAD,
    ),
)
