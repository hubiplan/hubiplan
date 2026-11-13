"""Erscheinungsbild der Einheit über die KI-Schnittstelle (docs/mcp.md): Farben, Namen und
Verwendung, weitere Farben, Verläufe, Farbrollen und Logo.

Anders als die Webseite hat das Erscheinungsbild keinen Entwurf: Änderungen gelten sofort für
HUBIplan und die Webseite (Ralf 13.11.2026). Die Werkzeuge rufen dieselben Ansichten wie
Einstellungen › Erscheinungsbild auf (Recht für das Erscheinungsbild, Prüfung der
Lesbarkeit, Änderungsprotokoll mit Rückgängig).
"""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from .club import ClubContext, _dump, _int, _schema
from .oauth import SCOPE_READ, SCOPE_THEME
from .tools import Tool, ToolError

MAX_EXTRA = 4
MAX_GRADIENTS = 2
ROLES = ("text", "muted", "surface", "background")


def _views():
    from organizations import views

    return views


def _theme(ctx: ClubContext) -> dict:
    return ctx.call(_views().ThemeView, "GET", "theme/")


def _summary(data: dict) -> dict:
    eff = data.get("effective") or {}
    own = bool(data.get("primary_color"))
    return {
        "eigene_farben": own,
        "palette": [
            {
                "platz": i,
                "farbe": p.get("color"),
                "name": p.get("name") or "",
                "verwendung": p.get("use") or "",
                "textfarbe_darauf": p.get("on_color"),
            }
            for i, p in enumerate(eff.get("palette") or [])
        ],
        "verlaeufe": [
            {
                "name": g.get("name") or "",
                "von": g.get("from"),
                "bis": g.get("to"),
                "richtung": g.get("direction"),
            }
            for g in eff.get("gradients") or []
        ],
        "farbrollen": data.get("palette_roles") or {},
        "farbrollen_in_hubiplan": bool(data.get("palette_roles_in_app")),
        "logo": bool(data.get("logo_url")),
        "logo_dunkel": bool(data.get("logo_dark_url")),
    }


def _read(args: dict, ctx: ClubContext) -> str:
    data = _theme(ctx)
    result = _summary(data)
    hint = _(
        "Erscheinungsbild der Einheit. Platz 0 ist die Hauptfarbe, 1 die Zweitfarbe, 2–5 "
        "weitere Farben. Farbrollen: text (Fließtext), muted (Sekundärtext), surface "
        "(Flächen), background (Seitenhintergrund), jeweils ein Palettenplatz."
    )
    if not result["eigene_farben"]:
        hint += " " + _(
            "Die Einheit hat noch keine eigenen Farben und erbt sie; wer eigene setzt, legt "
            "die ganze Palette neu fest."
        )
    return hint + "\n\n" + _dump(result)


def _color(value, name: str) -> dict:
    """{farbe, name, verwendung} → Felder der Schnittstelle (nur Angegebenes)."""
    if not isinstance(value, dict):
        raise ToolError(_("„%(name)s“ muss ein Objekt sein.") % {"name": name})
    return value


def _change(args: dict, ctx: ClubContext) -> str:
    body: dict = {}
    for arg, prefix in (("hauptfarbe", "primary"), ("zweitfarbe", "accent")):
        if arg not in args or args[arg] is None:
            continue
        value = _color(args[arg], arg)
        if "farbe" in value:
            body[f"{prefix}_color"] = (value["farbe"] or "").strip()
        if "name" in value:
            body[f"{prefix}_color_name"] = (value["name"] or "").strip()
        if "verwendung" in value:
            body[f"{prefix}_color_use"] = (value["verwendung"] or "").strip()
    if args.get("weitere_farben") is not None:
        extra = args["weitere_farben"]
        if not isinstance(extra, list):
            raise ToolError(_("„%(name)s“ muss eine Liste sein.") % {"name": "weitere_farben"})
        body["extra_colors"] = [
            {
                "color": (_color(e, "weitere_farben").get("farbe") or "").strip(),
                "name": e.get("name") or "",
                "use": e.get("verwendung") or "",
            }
            for e in extra
        ]
    if args.get("verlaeufe") is not None:
        grads = args["verlaeufe"]
        if not isinstance(grads, list):
            raise ToolError(_("„%(name)s“ muss eine Liste sein.") % {"name": "verlaeufe"})
        body["gradients"] = [
            {
                "name": _color(g, "verlaeufe").get("name") or "",
                "from": g.get("von"),
                "to": g.get("bis"),
                "direction": g.get("richtung") or "right",
            }
            for g in grads
        ]
    if args.get("farbrollen") is not None:
        roles = _color(args["farbrollen"], "farbrollen")
        current = _theme(ctx).get("palette_roles") or {}
        merged = {**current, **roles}
        body["palette_roles"] = {k: v for k, v in merged.items() if v is not None}
    if args.get("farbrollen_in_hubiplan") is not None:
        if not isinstance(args["farbrollen_in_hubiplan"], bool):
            raise ToolError(_("„farbrollen_in_hubiplan“ ist ja oder nein."))
        body["palette_roles_in_app"] = args["farbrollen_in_hubiplan"]
    if not body:
        raise ToolError(_("Bitte angeben, was sich am Erscheinungsbild ändern soll."))
    data = ctx.call(_views().ThemeView, "PATCH", "theme/", body)
    return (
        _(
            "Erscheinungsbild geändert ({keys}). Es gilt ab sofort in HUBIplan und auf der "
            "Webseite; zurücknehmen lässt es sich im Änderungsprotokoll mit „Rückgängig“."
        ).format(keys=", ".join(sorted(body)))
        + "\n\n"
        + _dump(_summary(data))
    )


def _logo(args: dict, ctx: ClubContext) -> str:
    from core.tenancy import rls_bypass
    from website import content_views
    from website.content_models import WebsiteImage

    pk = _int(args, "nummer")
    # Rechte auf das Bild wie in der Oberfläche prüfen, dann die Datei lesen
    ctx.call(content_views.ImageDetailView, "GET", f"website/images/{pk}/", pk=pk)
    with rls_bypass():
        image = WebsiteImage.objects.filter(pk=pk, organization_id=ctx.org_id).first()
    if image is None or not image.file.name:
        raise ToolError(_("Dieses Bild gibt es nicht."))
    with image.file.open("rb") as f:
        content = f.read()
    upload = SimpleUploadedFile(image.file.name.rsplit("/", 1)[-1], content)
    dark = args.get("dunkel") is True
    view = _views().OrganizationLogoDarkView if dark else _views().OrganizationLogoView
    form = {"logo": upload, "remove_background": bool(args.get("hintergrund_entfernen"))}
    ctx.call(view, "POST", "logo-dark/" if dark else "logo/", multipart=form)
    return (
        (_("Logo für den Dunkelmodus gesetzt.") if dark else _("Logo gesetzt."))
        + " "
        + _("Es gilt ab sofort in HUBIplan und auf der Webseite; das vorherige Logo ist ersetzt.")
    )


COLOR = {
    "type": "object",
    "properties": {
        "farbe": {"type": "string", "maxLength": 7, "description": "#rrggbb"},
        "name": {"type": "string", "maxLength": 30},
        "verwendung": {"type": "string", "maxLength": 60},
    },
}
SLOT = {"type": ["integer", "null"], "minimum": 0, "maximum": 5}

THEME_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="erscheinungsbild_ansehen",
        title=gettext_lazy("Erscheinungsbild ansehen"),
        description=gettext_lazy(
            "Farben der Einheit mit Namen und Verwendung, Verläufe, Farbrollen und ob ein Logo "
            "gesetzt ist (Einstellungen › Erscheinungsbild)."
        ),
        schema=_schema(),
        run=_read,
        scope=SCOPE_READ,
    ),
    Tool(
        name="erscheinungsbild_aendern",
        title=gettext_lazy("Erscheinungsbild ändern"),
        description=gettext_lazy(
            "Ändert Farben, Namen, Verwendung, weitere Farben, Verläufe und Farbrollen der "
            "Einheit. Gilt SOFORT für HUBIplan und Webseite, es gibt keinen Entwurf: vorher die "
            "Person fragen. Text auf jeder Farbe muss lesbar sein. Braucht das Recht, das "
            "Erscheinungsbild zu bearbeiten."
        ),
        schema=_schema(
            {
                "hauptfarbe": COLOR,
                "zweitfarbe": COLOR,
                "weitere_farben": {
                    "type": "array",
                    "maxItems": MAX_EXTRA,
                    "items": COLOR,
                    "description": gettext_lazy("Ersetzt alle weiteren Farben (Plätze 2–5)."),
                },
                "verlaeufe": {
                    "type": "array",
                    "maxItems": MAX_GRADIENTS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "maxLength": 30},
                            "von": {"type": "integer", "minimum": 0, "maximum": 5},
                            "bis": {"type": "integer", "minimum": 0, "maximum": 5},
                            "richtung": {"type": "string", "enum": ["right", "down"]},
                        },
                        "required": ["von", "bis"],
                    },
                    "description": gettext_lazy("Ersetzt alle Verläufe."),
                },
                "farbrollen": {
                    "type": "object",
                    "properties": {role: SLOT for role in ROLES},
                    "description": gettext_lazy("Rolle → Palettenplatz; null entfernt."),
                },
                "farbrollen_in_hubiplan": {"type": "boolean"},
            }
        ),
        run=_change,
        writes=True,
        scope=SCOPE_THEME,
    ),
    Tool(
        name="logo_aus_bild",
        title=gettext_lazy("Logo aus einem Bild setzen"),
        description=gettext_lazy(
            "Setzt ein Bild aus der Bilderverwaltung der Webseite als Logo (oder als Logo für "
            "den Dunkelmodus). Gilt sofort. Neue Bilder: bild_hochladen_vorbereiten."
        ),
        schema=_schema(
            {
                "nummer": {"type": "integer", "minimum": 1},
                "dunkel": {"type": "boolean"},
                "hintergrund_entfernen": {
                    "type": "boolean",
                    "description": gettext_lazy("Weißen Rand durchsichtig machen."),
                },
            },
            ["nummer"],
        ),
        run=_logo,
        writes=True,
        scope=SCOPE_THEME,
    ),
)
