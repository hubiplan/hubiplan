"""Werkzeuge der Stufen W2 und W3 (docs/mcp.md): Gestaltung, Menü, Aufbau der Startseite,
Bilder und Entwürfe für Social-Media-Beiträge.

Alles landet im Entwurf bzw. in der Bilderverwaltung; veröffentlicht wird nur in HUBIplan.
Die Werkzeuge rufen dieselben Ansichten wie die Oberfläche auf (``ClubContext.call``), damit
gelten dieselben Rechte: Gestaltung, Menü und Aufbau brauchen „Webseite verwalten“, Bilder und
Beitragsentwürfe „Inhalte bearbeiten“.
"""

from __future__ import annotations

import base64
import io
import secrets
import string

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from .club import ClubContext, _dump, _int, _schema, _str, _views
from .oauth import SCOPE_DRAFT, SCOPE_READ
from .tools import Tool, ToolError

IMAGE_PREVIEW = 640  # Kantenlänge des Bildes, das der Assistent zu sehen bekommt
MAX_NAME = 60
MAX_URL = 500
MAX_ALT = 300
MAX_SOCIAL = 2200

# Felder der eigenen Abschnitte (website/home.py ``_clean_data``), als Hilfe für den Assistenten
KIND_FIELDS = {
    "text": "title, text (Markdown)",
    "text_image": (
        "title, text (Markdown), image (Bildnummer), side (left|right), size (small|half)"
    ),
    "banner": "image (Bildnummer), line, height (low|high)",
    "buttons": "title, buttons [{label, target}] (höchstens 3), align (left|center|right)",
    "tiles": "title, tiles [{title, text, image, target}] (2–6), columns (2|3)",
    "event": "title, event (Terminnummer aus auswahl.events)",
    "album": "title, album (Albumnummer), count (4–8)",
    "quote": "text, name",
    "contacts": "title, roles [Rollennummern] (höchstens 4)",
    "faq": "title, items [{question, answer}] (höchstens 12)",
    "partners": "title, items [{name, image, url}] (höchstens 12)",
    "directions": "title, place (Ortsnummer), text",
    "event_list": "title, category (Kategorienummer), count (2–10)",
    "document": "title, document (Dokumentnummer), label",
    "video": "title, url, image (Bildnummer), text",
    "chronicle": "title, count (2–6)",
    "facts": "title, items [{value, label}] (2–6)",
    "divider": "style (line|space), size (small|large)",
}
TARGET_HINT = (
    'target: {"page": "<Menüschlüssel>"}, {"event": <Terminnummer>} oder {"url": "https://…"}'
)


def _site(ctx: ClubContext) -> tuple[dict, dict]:
    views, _c = _views()
    data = ctx.call(views.WebsiteView, "GET", "website/")
    site = data.get("website")
    if site is None:
        raise ToolError(_("Für diese Einheit ist noch keine Webseite eingerichtet."))
    return data, site


def _current(site: dict) -> dict:
    """Werte so, wie die Vorschau sie zeigt: Entwurf über dem veröffentlichten Stand."""
    return {**site, **(site.get("draft") or {})}


def _save_draft(ctx: ClubContext, draft: dict) -> dict:
    views, _c = _views()
    data = ctx.call(views.WebsiteView, "PUT", "website/", {"draft": draft})
    return data.get("website") or {}


def _draft_hint() -> str:
    return _(
        "Im Entwurf gespeichert. Sichtbar ist es erst, wenn jemand den Entwurf in HUBIplan "
        "unter Webseite veröffentlicht. Ansehen mit webseite_vorschau."
    )


def _obj(args: dict, name: str) -> dict | None:
    if name not in args or args[name] is None:
        return None
    value = args[name]
    if not isinstance(value, dict):
        raise ToolError(_("„%(name)s“ muss ein Objekt sein.") % {"name": name})
    return value


def _list(args: dict, name: str) -> list | None:
    if name not in args or args[name] is None:
        return None
    value = args[name]
    if not isinstance(value, list):
        raise ToolError(_("„%(name)s“ muss eine Liste sein.") % {"name": name})
    return value


# --- Gestaltung ---


def _design_read(args: dict, ctx: ClubContext) -> str:
    data, site = _site(ctx)
    v = _current(site)
    design = v.get("design")
    catalog = data.get("designs") or []
    chosen = next((d for d in catalog if d["key"] == design), None)
    style_catalog = data.get("style_catalog") or {}
    result = {
        "design": design,
        "designs": [
            {"schluessel": d["key"], "name": d["label"], "hinweis": d["hint"]} for d in catalog
        ],
        "farbrollen": [
            {
                "rolle": r["key"],
                "name": r["label"],
                "wahl": (v.get("color_roles") or {}).get(design, {}).get(r["key"]),
                "verlauf_moeglich": r.get("gradient", False),
            }
            for r in (chosen or {}).get("roles", [])
        ],
        "palette": [
            {"platz": i, "farbe": p["color"], "name": p.get("name") or ""}
            for i, p in enumerate(data.get("palette") or [])
        ],
        "verlaeufe": [f"g{i}" for i, _g in enumerate(data.get("gradients") or [])],
        "stil": v.get("style") or {},
        "stilregler": style_catalog.get("options", {}),
        "vom_design_gesperrt": (style_catalog.get("locks") or {}).get(design, {}),
        "darstellung": v.get("layouts") or {},
        "darstellungen": [
            {"bereich": a["area"], "varianten": [x["key"] for x in a["variants"]]}
            for a in data.get("layout_catalog") or []
        ],
        "kopfbild": v.get("header_image"),
        "kopfbild_schmal": v.get("header_image_narrow"),
        "im_entwurf": sorted((site.get("draft") or {}).keys()),
        "darf_gestalten": data.get("can_manage"),
    }
    return (
        _(
            "Gestaltung im Entwurf. Farben: Palettenplatz (Zahl), „dark“, „light“ oder ein "
            "Verlauf (g0, g1, nur wo verlauf_moeglich). Stilregler: Stufe aus stilregler, "
            "„switch“ heißt ja/nein, null setzt auf das Design zurück."
        )
        + "\n\n"
        + _dump(result)
    )


def _design_change(args: dict, ctx: ClubContext) -> str:
    _data, site = _site(ctx)
    v = _current(site)
    draft: dict = {}
    design = _str(args, "design", 40)
    if design is not None:
        draft["design"] = design
    target = design or v.get("design")
    style = _obj(args, "stil")
    if style is not None:
        merged = {**(v.get("style") or {}), **style}
        draft["style"] = {k: x for k, x in merged.items() if x is not None}
    colors = _obj(args, "farben")
    if colors is not None:
        roles = {k: dict(x) for k, x in (v.get("color_roles") or {}).items()}
        mine = {**roles.get(target, {}), **colors}
        roles[target] = {k: x for k, x in mine.items() if x is not None}
        draft["color_roles"] = roles
    layouts = _obj(args, "darstellung")
    if layouts is not None:
        merged = {**(v.get("layouts") or {}), **layouts}
        draft["layouts"] = {k: x for k, x in merged.items() if x is not None}
    if "kopfbild" in args:
        value = args["kopfbild"]
        if value is not None:
            value = _int(args, "kopfbild")
        draft["header_image"] = value
    if "kopfbild_schmal" in args:
        value = args["kopfbild_schmal"]
        if value is not None:
            value = _int(args, "kopfbild_schmal")
        draft["header_image_narrow"] = value
    if not draft:
        raise ToolError(_("Bitte angeben, was sich ändern soll (design, stil, farben, …)."))
    saved = _save_draft(ctx, draft)
    return (
        _("Gestaltung geändert ({keys}).").format(keys=", ".join(sorted(draft)))
        + " "
        + _draft_hint()
        + "\n\n"
        + _dump({"im_entwurf": sorted((saved.get("draft") or {}).keys())})
    )


# --- Menü ---


def _menu_names(site: dict, v: dict) -> dict[str, dict]:
    """Alle Menüpunkte mit Namen aus dem Entwurf (auch neue Überschriften und Links)."""
    names = v.get("block_names") or {}
    links = v.get("menu_links") or {}
    items = {}
    for item in site.get("menu_items") or []:
        key = item["key"]
        label = names.get(key) if item.get("renamable") else None
        items[key] = {
            "name": label or item.get("default_label") or item.get("label"),
            "standardname": item.get("default_label"),
            "umbenennbar": bool(item.get("renamable")),
            "ueberschrift": bool(item.get("heading")),
            "baustein": item.get("toggle"),
        }
    for key, name in names.items():
        if key.startswith(("heading:", "link:")):
            items[key] = {
                "name": name,
                "umbenennbar": True,
                "ueberschrift": key.startswith("heading:"),
            }
    for key, url in links.items():
        if key in items:
            items[key]["adresse"] = url
    return items


def _menu_read(args: dict, ctx: ClubContext) -> str:
    _data, site = _site(ctx)
    v = _current(site)
    items = _menu_names(site, v)
    blocks = site.get("blocks") or {}

    def node(n: dict) -> dict:
        info = items.get(n["key"], {})
        row = {"schluessel": n["key"], "name": info.get("name", n["key"])}
        if info.get("baustein"):
            row["an"] = bool(blocks.get(info["baustein"], True))
        if info.get("adresse"):
            row["adresse"] = info["adresse"]
        if n.get("children"):
            row["unterpunkte"] = [node(c) for c in n["children"]]
        return row

    result = {
        "menue": [node(n) for n in v.get("menu") or []],
        "knopf": v.get("menu_button") or "",
        # Webseite #75: Hauptpunkte nur im Fuß oder im Menü und im Fuß
        "fuss": {
            k: PLACE_NAMES[p] for k, p in (v.get("menu_places") or {}).items() if p in PLACE_NAMES
        },
        "punkte": [{"schluessel": k, **x} for k, x in items.items()],
    }
    return (
        _(
            "Menü im Entwurf (zwei Ebenen). „an“: Baustein eingeschaltet; ein- und ausschalten "
            "geht nur in HUBIplan. Ändern mit webseite_menue_aendern."
        )
        + "\n\n"
        + _dump(result)
    )


# Platz eines Hauptpunkts (Webseite #75): Wert in HUBIplan → Wort für das Werkzeug
PLACE_NAMES = {"footer": "fuss", "both": "beides"}
PLACE_VALUES = {"fuss": "footer", "beides": "both", "menue": None}


def _tree(value) -> list[dict]:
    if not isinstance(value, list):
        raise ToolError(_("„reihenfolge“ muss eine Liste sein."))
    tree = []
    for n in value:
        if isinstance(n, str):
            n = {"schluessel": n}
        if not isinstance(n, dict) or not isinstance(n.get("schluessel"), str):
            raise ToolError(_("Jeder Menüpunkt braucht einen „schluessel“."))
        children = []
        for c in n.get("unterpunkte") or []:
            key = c if isinstance(c, str) else c.get("schluessel") if isinstance(c, dict) else None
            if not isinstance(key, str):
                raise ToolError(_("Jeder Menüpunkt braucht einen „schluessel“."))
            children.append({"key": key, "children": []})
        tree.append({"key": n["schluessel"], "children": children})
    return tree


def _next_key(names: dict, prefix: str) -> str:
    used = [
        int(k.split(":", 1)[1])
        for k in names
        if k.startswith(prefix + ":") and k.split(":", 1)[1].isdigit()
    ]
    return f"{prefix}:{max([0, *used]) + 1}"


def _menu_change(args: dict, ctx: ClubContext) -> str:
    _data, site = _site(ctx)
    v = _current(site)
    names = dict(v.get("block_names") or {})
    links = dict(v.get("menu_links") or {})
    menu = list(v.get("menu") or [])
    button = v.get("menu_button") or ""
    places = dict(v.get("menu_places") or {})
    created = []
    for entry in _list(args, "neu") or []:
        if not isinstance(entry, dict) or entry.get("art") not in ("ueberschrift", "link"):
            raise ToolError(_("Neue Punkte: art „ueberschrift“ oder „link“ mit name."))
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > MAX_NAME:
            raise ToolError(_("Neue Punkte brauchen einen Namen (höchstens 60 Zeichen)."))
        prefix = "heading" if entry["art"] == "ueberschrift" else "link"
        key = _next_key(names, prefix)
        names[key] = name.strip()
        if prefix == "link":
            url = entry.get("adresse")
            if not isinstance(url, str) or len(url) > MAX_URL:
                raise ToolError(_("Ein Link braucht eine „adresse“ mit https://."))
            links[key] = url.strip()
        created.append(key)
    for key, name in (_obj(args, "namen") or {}).items():
        if name is None or name == "":
            names.pop(key, None)
            links.pop(key, None)
        elif not isinstance(name, str) or len(name) > MAX_NAME:
            raise ToolError(_("Namen höchstens 60 Zeichen."))
        else:
            names[key] = name
    for key, url in (_obj(args, "links") or {}).items():
        if not isinstance(url, str) or len(url) > MAX_URL:
            raise ToolError(_("Ein Link braucht eine „adresse“ mit https://."))
        links[key] = url
    if "reihenfolge" in args:
        menu = _tree(args["reihenfolge"])
    if "knopf" in args:
        button = _str(args, "knopf", 40) or ""
    for key, place in (_obj(args, "fuss") or {}).items():
        if place not in PLACE_VALUES:
            raise ToolError(_("Platz im Fuß: „fuss“, „beides“ oder „menue“."))
        if PLACE_VALUES[place]:
            places[key] = PLACE_VALUES[place]
        else:
            places.pop(key, None)
    if not created and not any(
        k in args for k in ("namen", "links", "reihenfolge", "knopf", "fuss")
    ):
        raise ToolError(_("Bitte angeben, was sich am Menü ändern soll."))
    _save_draft(
        ctx,
        {
            "menu": menu,
            "block_names": names,
            "menu_links": links,
            "menu_button": button,
            "menu_places": places,
        },
    )
    text = _("Menü geändert.") + " " + _draft_hint()
    if created:
        text += "\n\n" + _dump({"neue_schluessel": created})
    return text


# --- Aufbau der Startseite ---


def _new_key(taken: set[str]) -> str:
    alphabet = string.ascii_lowercase + string.digits
    while True:
        key = "c:" + "".join(secrets.choice(alphabet) for _i in range(8))
        if key not in taken:
            return key


LOOK = {"hintergrund": "bg", "breite": "width", "spalte": "column"}


def _rebuild(sections: list[dict], args: dict) -> tuple[list[dict], list[str]]:
    """Aufbau einer Folge von Abschnitten ändern (Startseite und Textseiten, #78)."""
    sections = [dict(s) for s in sections]
    by_key = {s["key"]: s for s in sections}
    changed = False
    created = []
    for key in _list(args, "entfernen") or []:
        s = by_key.get(key)
        if s is None or "kind" not in s:
            raise ToolError(_("Entfernen geht nur bei eigenen Abschnitten: {key}").format(key=key))
        sections.remove(s)
        by_key.pop(key)
        changed = True
    for entry in _list(args, "neu") or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("art"), str):
            raise ToolError(_("Neue Abschnitte brauchen eine „art“."))
        content = entry.get("inhalt") or {}
        if not isinstance(content, dict):
            raise ToolError(_("„inhalt“ muss ein Objekt mit den geänderten Feldern sein."))
        key = _new_key(set(by_key))
        new = {"key": key, "on": entry.get("an", True) is not False, "kind": entry["art"]}
        new["data"] = content
        after = entry.get("nach")
        at = len(sections)
        if isinstance(after, str) and after in by_key:
            at = sections.index(by_key[after]) + 1
        elif after == "":
            at = 0
        sections.insert(at, new)
        by_key[key] = new
        created.append(key)
        changed = True
    order = _list(args, "reihenfolge")
    if order is not None:
        known = [k for k in order if k in by_key]
        rest = [s for s in sections if s["key"] not in known]
        sections = [by_key[k] for k in dict.fromkeys(known)] + rest
        changed = True
    for key in _list(args, "an") or []:
        if key in by_key:
            by_key[key]["on"] = True
            changed = True
    for key in _list(args, "aus") or []:
        if key in by_key:
            by_key[key]["on"] = False
            changed = True
    for key, look in (_obj(args, "aussehen") or {}).items():
        if key not in by_key or not isinstance(look, dict):
            raise ToolError(_("Diesen Abschnitt gibt es nicht: {key}").format(key=key))
        for name, field in LOOK.items():
            if name in look:
                by_key[key][field] = look[name]
        changed = True
    if not changed:
        raise ToolError(_("Bitte angeben, was sich am Aufbau ändern soll."))
    return sections, created


def _home_build(args: dict, ctx: ClubContext) -> str:
    _data, site = _site(ctx)
    v = _current(site)
    sections, created = _rebuild(v.get("home_sections") or [], args)
    _save_draft(ctx, {"home_sections": sections})
    text = _("Aufbau der Startseite geändert.") + " " + _draft_hint()
    if created:
        text += "\n\n" + _dump({"neue_schluessel": created})
    return text


# --- Abschnitte einer Textseite (#78) ---


def _page_sections(ctx: ClubContext, pk: int) -> list[dict]:
    _v, content_views = _views()
    t = ctx.call(content_views.TextDetailView, "GET", f"website/texts/{pk}/", pk=pk)
    if t.get("kind") != "page" or t.get("has_timeline"):
        raise ToolError(
            _("Abschnitte gibt es nur auf Textseiten (nicht in der Chronik mit Zeitleiste).")
        )
    return list(t.get("sections") or [])


def _save_page_sections(ctx: ClubContext, pk: int, sections: list[dict]) -> dict:
    _v, content_views = _views()
    return ctx.call(
        content_views.TextDetailView, "PUT", f"website/texts/{pk}/", {"sections": sections}, pk=pk
    )


def _page_build(args: dict, ctx: ClubContext) -> str:
    pk = _int(args, "nummer")
    sections, created = _rebuild(_page_sections(ctx, pk), args)
    t = _save_page_sections(ctx, pk, sections)
    text = (
        _("Aufbau der Textseite „{title}“ geändert.").format(title=t.get("title", ""))
        + " "
        + _draft_hint()
    )
    if created:
        text += "\n\n" + _dump({"neue_schluessel": created})
    return text


def _page_section_change(args: dict, ctx: ClubContext) -> str:
    pk = _int(args, "nummer")
    key = _str(args, "schluessel", 40, required=True)
    content = args.get("inhalt")
    if not isinstance(content, dict) or not content:
        raise ToolError(_("„inhalt“ muss ein Objekt mit den geänderten Feldern sein."))
    sections = [dict(s) for s in _page_sections(ctx, pk)]
    target = next((s for s in sections if s.get("key") == key), None)
    if target is None:
        raise ToolError(_("Diesen Abschnitt gibt es nicht. Erst webseite_text_lesen aufrufen."))
    if "kind" not in target:
        raise ToolError(
            _("Den Text der Seite ändert webseite_text_aendern; er hat hier keinen Inhalt.")
        )
    target["data"] = {**(target.get("data") or {}), **content}
    _save_page_sections(ctx, pk, sections)
    return _("Abschnitt {key} der Textseite geändert.").format(key=key) + " " + _draft_hint()


def _home_options(args: dict, ctx: ClubContext) -> str:
    data, _site_data = _site(ctx)
    kinds = data.get("home_kinds") or {}
    hints = data.get("home_kind_hints") or {}
    choices = data.get("home_choices") or {}
    result = {
        "arten": [
            {
                "art": k,
                "name": str(name),
                "hinweis": str(hints.get(k, "")),
                "felder": KIND_FIELDS.get(k, ""),
            }
            for k, name in kinds.items()
        ],
        "ziele": TARGET_HINT,
        "aussehen": {
            "hintergrund": "none, light, p0–p9 (Palette), g0, g1 (Verlauf)",
            "breite": "content, text, full",
            "spalte": "main, side (nur Design „Zeitung“)",
        },
        "auswahl": choices,
    }
    return (
        _(
            "Arten eigener Abschnitte mit ihren Feldern und die Nummern, auf die sie verweisen "
            "können (Rollen, Alben, Termine, Orte, Kategorien, Dokumente). Bilder: "
            "webseite_bilder."
        )
        + "\n\n"
        + _dump(result)
    )


# --- Bilder ---


def _image_search(args: dict, ctx: ClubContext) -> str:
    _v, content_views = _views()
    data = ctx.call(content_views.ImageListView, "GET", "website/images/") or []
    query = (_str(args, "suche", 100) or "").strip().lower()
    rows = []
    for i in data:
        text = " ".join(
            str(x or "")
            for x in (
                i.get("caption"),
                i.get("alt_text"),
                i.get("file_name"),
                i.get("department_name"),
            )
        ).lower()
        if query and not all(word in text for word in query.split()):
            continue
        rows.append(
            {
                "nummer": i["id"],
                "schluessel": i["key"],
                "alternativtext": i.get("alt_text") or "",
                "bildunterschrift": i.get("caption") or "",
                "dekorativ": i.get("decorative"),
                "datei": i.get("file_name") or "",
                "gehoert_zu": i.get("department_name"),
                "aufgenommen": i.get("taken_at"),
                "benutzt": i.get("used"),
                "markdown": i.get("markdown"),
                "breite": i.get("width"),
                "hoehe": i.get("height"),
            }
        )
    return (
        _(
            "Bilder der Webseite (neueste zuerst). Ansehen mit bild_ansehen, Texte dazu mit "
            "bild_beschreiben. In Texten mit der Markdown-Zeile einbinden, in Abschnitten mit "
            "der Nummer."
        )
        + "\n\n"
        + _dump(rows[:200])
    )


def _image_view(args: dict, ctx: ClubContext):
    from PIL import Image

    from core.tenancy import rls_bypass
    from website.content_models import WebsiteImage

    _v, content_views = _views()
    pk = _int(args, "nummer")
    # Rechte wie in der Oberfläche prüfen, dann die kleine Fassung lesen
    info = ctx.call(content_views.ImageDetailView, "GET", f"website/images/{pk}/", pk=pk)
    with rls_bypass():
        image = WebsiteImage.objects.filter(pk=pk, organization_id=ctx.org_id).first()
    if image is None or not image.small.name:
        raise ToolError(_("Dieses Bild gibt es nicht."))
    with image.small.open("rb") as f, Image.open(f) as img:
        img = img.convert("RGB")
        img.thumbnail((IMAGE_PREVIEW, IMAGE_PREVIEW))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=80)
    meta = {
        "nummer": info["id"],
        "alternativtext": info.get("alt_text") or "",
        "bildunterschrift": info.get("caption") or "",
        "benutzt": info.get("usage") or [],
    }
    note = _(
        "Beschreibe nur, was zu sehen ist. Erkenne oder benenne keine Personen; Namen kommen nur "
        "aus HUBIplan."
    )
    return [
        {
            "type": "image",
            "data": base64.b64encode(out.getvalue()).decode(),
            "mimeType": "image/jpeg",
        },
        {"type": "text", "text": note + "\n\n" + _dump(meta)},
    ]


def _image_describe(args: dict, ctx: ClubContext) -> str:
    _v, content_views = _views()
    pk = _int(args, "nummer")
    info = ctx.call(content_views.ImageDetailView, "GET", f"website/images/{pk}/", pk=pk)
    body = {}
    for arg, field in (("alternativtext", "alt_text"), ("bildunterschrift", "caption")):
        value = _str(args, arg, MAX_ALT)
        if value is None:
            continue
        # Benutzte Bilder: vorhandene Texte nur in HUBIplan ändern (wirkt sofort öffentlich)
        if info.get("used") and (info.get(field) or "").strip():
            raise ToolError(
                _(
                    "Das Bild ist schon in Gebrauch und hat einen {name}. Den ändert jemand in "
                    "HUBIplan unter Webseite › Bilder."
                ).format(name=arg)
            )
        body[field] = value.strip()
    if not body:
        raise ToolError(_("Bitte alternativtext oder bildunterschrift angeben."))
    ctx.call(content_views.ImageDetailView, "PUT", f"website/images/{pk}/", body, pk=pk)
    hint = (
        _("Das Bild ist schon in Gebrauch; der neue Text gilt dort sofort.")
        if info.get("used")
        else _(
            "Gespeichert. Öffentlich wird das Bild erst, wenn es in einem veröffentlichten "
            "Text oder Abschnitt steht."
        )
    )
    return _("Texte zu Bild {pk} gespeichert.").format(pk=pk) + " " + hint


def _upload_link(args: dict, ctx: ClubContext) -> str:
    from website import upload_views

    data = ctx.call(
        upload_views.ImageUploadLinkView,
        "POST",
        "website/images/upload-link/",
        {"via": _via(ctx)},
    )
    return _(
        "Link zum Hochladen (gültig bis {until}, höchstens {n} Bilder): {url}\n\nGib den Link "
        "der Person weiter. Sie öffnet ihn auf Handy oder PC und wählt Fotos; die Dateien gehen "
        "nicht über den Chat. Danach findest du die neuen Bilder mit webseite_bilder."
    ).format(until=_time(data.get("expires_at")), n=data.get("max_files"), url=data.get("url"))


def _image_fetch(args: dict, ctx: ClubContext) -> str:
    from website import upload_views

    body = {
        "url": _str(args, "adresse", 2000, required=True),
        "source": _str(args, "quelle", 200, required=True),
        "caption": _str(args, "bildunterschrift", MAX_ALT) or "",
        "alt_text": _str(args, "alternativtext", MAX_ALT) or "",
    }
    data = ctx.call(upload_views.ImageFetchView, "POST", "website/images/fetch/", body)
    return _("Bild als Nummer {pk} in der Bilderverwaltung gespeichert ({markdown}).").format(
        pk=data["id"], markdown=data.get("markdown")
    )


def _via(ctx: ClubContext) -> str:
    return f"KI-Assistent ({ctx.grant.client.name})"[:120]


def _time(value) -> str:
    from django.utils import timezone
    from django.utils.dateparse import parse_datetime

    moment = parse_datetime(value) if isinstance(value, str) else value
    return f"{timezone.localtime(moment):%d.%m.%Y %H:%M}" if moment else ""


# --- Social Media ---


def _social_draft(args: dict, ctx: ClubContext) -> str:
    from website import social_views

    text = _str(args, "text", MAX_SOCIAL, required=True)
    images = _list(args, "bilder") or []
    if not all(isinstance(i, int) and not isinstance(i, bool) for i in images):
        raise ToolError(_("„bilder“ ist eine Liste von Bildnummern."))
    channel = _str(args, "kanal", 10) or ""
    data = ctx.call(
        social_views.SocialDraftListView,
        "POST",
        "website/social/drafts/",
        {"text": text, "images": images, "channel": channel, "via": _via(ctx)},
    )
    return _(
        "Entwurf {pk} gespeichert. Die Person findet ihn in HUBIplan unter Webseite › "
        "Social Media, kopiert Text und Bilder und postet selbst; HUBIplan veröffentlicht nichts "
        "bei Instagram oder Facebook."
    ).format(pk=data["id"])


def _social_list(args: dict, ctx: ClubContext) -> str:
    from website import social_views

    data = ctx.call(social_views.SocialDraftListView, "GET", "website/social/drafts/")
    rows = [
        {
            "nummer": d["id"],
            "kanal": d["channel"],
            "text": d["text"],
            "bilder": [i["id"] for i in d["images"]],
            "erledigt": bool(d["done_at"]),
        }
        for d in data.get("drafts", [])
    ]
    return _("Entwürfe für Social-Media-Beiträge, neueste zuerst.") + "\n\n" + _dump(rows)


NUMBER = {"type": "integer", "minimum": 1}
OPEN_OBJECT = {"type": "object"}
KEYS = {"type": "array", "items": {"type": "string", "maxLength": 40}, "maxItems": 60}

DESIGN_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="webseite_gestaltung_ansehen",
        title=gettext_lazy("Gestaltung ansehen"),
        description=gettext_lazy(
            "Design, Farben, Stilregler, Darstellung der Bereiche und Kopfbild im Entwurf, mit "
            "allen erlaubten Werten."
        ),
        schema=_schema(),
        run=_design_read,
        scope=SCOPE_READ,
    ),
    Tool(
        name="webseite_gestaltung_aendern",
        title=gettext_lazy("Gestaltung ändern (Entwurf)"),
        description=gettext_lazy(
            "Ändert Design, Farben, Stilregler, Darstellung oder Kopfbild im Entwurf. Nur "
            "angegebene Werte ändern sich; null setzt einen Wert zurück. Werte aus "
            "webseite_gestaltung_ansehen. Braucht das Recht „Webseite verwalten“."
        ),
        schema=_schema(
            {
                "design": {"type": "string", "maxLength": 40},
                "stil": {
                    "type": "object",
                    "description": gettext_lazy("Stilregler → Stufe, ja/nein oder null."),
                },
                "farben": {
                    "type": "object",
                    "description": gettext_lazy(
                        "Farbrolle → Palettenplatz, „dark“, „light“, g0, g1 oder null (für das "
                        "gewählte Design)."
                    ),
                },
                "darstellung": {
                    "type": "object",
                    "description": gettext_lazy("Bereich → Variante oder null."),
                },
                "kopfbild": {
                    "type": ["integer", "null"],
                    "description": gettext_lazy("Bildnummer oder null (Wappen und Name)."),
                },
                "kopfbild_schmal": {
                    "type": ["integer", "null"],
                    "description": gettext_lazy(
                        "Bildnummer eines Kopfbilds für Handys (unter 600 px Breite) oder null "
                        "(überall das Kopfbild)."
                    ),
                },
            }
        ),
        run=_design_change,
        writes=True,
        scope=SCOPE_DRAFT,
    ),
    Tool(
        name="webseite_menue_ansehen",
        title=gettext_lazy("Menü ansehen"),
        description=gettext_lazy(
            "Menü der Webseite im Entwurf: Reihenfolge, Unterpunkte, Namen, Links nach außen "
            "und der als Knopf hervorgehobene Punkt."
        ),
        schema=_schema(),
        run=_menu_read,
        scope=SCOPE_READ,
    ),
    Tool(
        name="webseite_menue_aendern",
        title=gettext_lazy("Menü ändern (Entwurf)"),
        description=gettext_lazy(
            "Ordnet das Menü im Entwurf: Reihenfolge mit Unterpunkten, eigene Namen, neue "
            "Überschriften und Links nach außen, Knopf, Platz im Fuß. Bausteine ein- oder "
            "ausschalten geht nur in HUBIplan. Braucht das Recht „Webseite verwalten“."
        ),
        schema=_schema(
            {
                "reihenfolge": {
                    "type": "array",
                    "maxItems": 60,
                    "items": {
                        "type": "object",
                        "properties": {
                            "schluessel": {"type": "string", "maxLength": 40},
                            "unterpunkte": KEYS,
                        },
                        "required": ["schluessel"],
                    },
                    "description": gettext_lazy(
                        "Hauptpunkte in neuer Reihenfolge; fehlende kommen an ihren Standardplatz."
                    ),
                },
                "namen": {
                    "type": "object",
                    "description": gettext_lazy("Schlüssel → eigener Name; leer = Standardname."),
                },
                "links": {
                    "type": "object",
                    "description": gettext_lazy("Schlüssel eines Links → https-Adresse."),
                },
                "neu": {
                    "type": "array",
                    "maxItems": 10,
                    "items": {
                        "type": "object",
                        "properties": {
                            "art": {"type": "string", "enum": ["ueberschrift", "link"]},
                            "name": {"type": "string", "maxLength": MAX_NAME},
                            "adresse": {"type": "string", "maxLength": MAX_URL},
                        },
                        "required": ["art", "name"],
                    },
                },
                "knopf": {
                    "type": "string",
                    "maxLength": 40,
                    "description": gettext_lazy("Hauptpunkt als Knopf; leer = keiner."),
                },
                "fuss": {
                    "type": "object",
                    "additionalProperties": {"type": "string", "enum": ["fuss", "beides", "menue"]},
                    "description": gettext_lazy(
                        "Schlüssel eines Hauptpunkts → „fuss“ (nur im Fuß, z. B. Kontakt neben "
                        "dem Impressum), „beides“ (Menü und Fuß) oder „menue“ (nur im Menü)."
                    ),
                },
            }
        ),
        run=_menu_change,
        writes=True,
        scope=SCOPE_DRAFT,
    ),
    Tool(
        name="startseite_bausteine",
        title=gettext_lazy("Abschnittsarten und Auswahl"),
        description=gettext_lazy(
            "Welche eigenen Abschnitte es gibt, welche Felder sie haben und welche Rollen, "
            "Alben, Termine, Orte, Kategorien und Dokumente sie zeigen können."
        ),
        schema=_schema(),
        run=_home_options,
        scope=SCOPE_READ,
    ),
    Tool(
        name="startseite_aufbau_aendern",
        title=gettext_lazy("Aufbau der Startseite ändern (Entwurf)"),
        description=gettext_lazy(
            "Neue eigene Abschnitte, Reihenfolge, an/aus, Aussehen und Entfernen eigener "
            "Abschnitte im Entwurf. Felder je Art: startseite_bausteine. Braucht das Recht "
            "„Webseite verwalten“."
        ),
        schema=_schema(
            {
                "neu": {
                    "type": "array",
                    "maxItems": 10,
                    "items": {
                        "type": "object",
                        "properties": {
                            "art": {"type": "string", "maxLength": 20},
                            "inhalt": OPEN_OBJECT,
                            "nach": {
                                "type": "string",
                                "maxLength": 40,
                                "description": gettext_lazy(
                                    "Schlüssel des Abschnitts davor; leer = ganz oben, fehlt = "
                                    "ganz unten."
                                ),
                            },
                            "an": {"type": "boolean"},
                        },
                        "required": ["art"],
                    },
                },
                "reihenfolge": KEYS,
                "an": KEYS,
                "aus": KEYS,
                "entfernen": KEYS,
                "aussehen": {
                    "type": "object",
                    "description": gettext_lazy(
                        "Schlüssel → {hintergrund, breite, spalte}, Werte aus startseite_bausteine."
                    ),
                },
            }
        ),
        run=_home_build,
        writes=True,
        scope=SCOPE_DRAFT,
    ),
    Tool(
        name="textseite_aufbau_aendern",
        title=gettext_lazy("Aufbau einer Textseite ändern (Entwurf)"),
        description=gettext_lazy(
            "Abschnitte einer Textseite wie auf der Startseite: neue eigene Abschnitte (z. B. "
            "Kacheln, Text mit Bild, Knopfleiste, Ansprechpartner; dazu „cover“ = Titelbild mit "
            "inhalt {image}, höchstens eins), Reihenfolge, an/aus, Aussehen und Entfernen. Der "
            "Text der Seite ist der feste Abschnitt „body“ (ändern mit webseite_text_aendern). "
            "Schlüssel liefert webseite_text_lesen, Felder je Art startseite_bausteine."
        ),
        schema=_schema(
            {
                "nummer": {
                    "type": "integer",
                    "minimum": 1,
                    "description": gettext_lazy("Nummer der Textseite."),
                },
                "neu": {
                    "type": "array",
                    "maxItems": 10,
                    "items": {
                        "type": "object",
                        "properties": {
                            "art": {"type": "string", "maxLength": 20},
                            "inhalt": OPEN_OBJECT,
                            "nach": {
                                "type": "string",
                                "maxLength": 40,
                                "description": gettext_lazy(
                                    "Schlüssel des Abschnitts davor; leer = ganz oben, fehlt = "
                                    "ganz unten."
                                ),
                            },
                            "an": {"type": "boolean"},
                        },
                        "required": ["art"],
                    },
                },
                "reihenfolge": KEYS,
                "an": KEYS,
                "aus": KEYS,
                "entfernen": KEYS,
                "aussehen": {
                    "type": "object",
                    "description": gettext_lazy(
                        "Schlüssel → {hintergrund, breite}, Werte aus startseite_bausteine. "
                        "Auch für „body“, z. B. breite full für Text über die volle Breite."
                    ),
                },
            },
            ["nummer"],
        ),
        run=_page_build,
        writes=True,
        scope=SCOPE_DRAFT,
    ),
    Tool(
        name="textseite_abschnitt_aendern",
        title=gettext_lazy("Abschnitt einer Textseite ändern (Entwurf)"),
        description=gettext_lazy(
            "Ändert den Inhalt eines eigenen Abschnitts einer Textseite im Entwurf. „inhalt“ "
            "enthält nur die geänderten Felder, aufgebaut wie „data“ aus webseite_text_lesen."
        ),
        schema=_schema(
            {
                "nummer": {
                    "type": "integer",
                    "minimum": 1,
                    "description": gettext_lazy("Nummer der Textseite."),
                },
                "schluessel": {
                    "type": "string",
                    "maxLength": 40,
                    "description": gettext_lazy("Schlüssel des Abschnitts, z. B. c:ab12."),
                },
                "inhalt": OPEN_OBJECT,
            },
            ["nummer", "schluessel", "inhalt"],
        ),
        run=_page_section_change,
        writes=True,
        scope=SCOPE_DRAFT,
    ),
    Tool(
        name="bilder_suchen",
        title=gettext_lazy("Bilder suchen"),
        description=gettext_lazy(
            "Sucht Bilder der Webseite nach Bildunterschrift, Alternativtext, Dateiname und "
            "Untereinheit; ohne Suchwort alle."
        ),
        schema=_schema({"suche": {"type": "string", "maxLength": 100}}),
        run=_image_search,
        scope=SCOPE_READ,
    ),
    Tool(
        name="bild_ansehen",
        title=gettext_lazy("Bild ansehen"),
        description=gettext_lazy(
            "Zeigt ein Bild der Webseite in kleiner Größe, z. B. um einen Alternativtext "
            "vorzuschlagen."
        ),
        schema=_schema({"nummer": NUMBER}, ["nummer"]),
        run=_image_view,
        scope=SCOPE_READ,
    ),
    Tool(
        name="bild_beschreiben",
        title=gettext_lazy("Bild beschreiben"),
        description=gettext_lazy(
            "Setzt Alternativtext und/oder Bildunterschrift eines Bildes. Bei Bildern, die schon "
            "auf der Webseite stehen, nur, wenn der Text noch fehlt."
        ),
        schema=_schema(
            {
                "nummer": NUMBER,
                "alternativtext": {"type": "string", "maxLength": MAX_ALT},
                "bildunterschrift": {"type": "string", "maxLength": MAX_ALT},
            },
            ["nummer"],
        ),
        run=_image_describe,
        writes=True,
        scope=SCOPE_DRAFT,
    ),
    Tool(
        name="bild_hochladen_vorbereiten",
        title=gettext_lazy("Link zum Hochladen von Bildern"),
        description=gettext_lazy(
            "Liefert einen persönlichen Link (30 Minuten, bis 20 Bilder), über den die Person "
            "Fotos in die Bilderverwaltung lädt, ohne sie in den Chat zu geben."
        ),
        schema=_schema(),
        run=_upload_link,
        writes=True,
        scope=SCOPE_DRAFT,
    ),
    Tool(
        name="bild_von_adresse",
        title=gettext_lazy("Bild von einer Adresse holen"),
        description=gettext_lazy(
            "Holt ein JPG-, PNG- oder WebP-Bild von einem Server, den die Einheit freigegeben "
            "hat (Webseite › Internetadresse), in die Bilderverwaltung. Quelle und Lizenz sind "
            "Pflicht und kommen in die Bildunterschrift."
        ),
        schema=_schema(
            {
                "adresse": {"type": "string", "maxLength": 2000},
                "quelle": {
                    "type": "string",
                    "maxLength": 200,
                    "description": gettext_lazy("Urheber und Lizenz, z. B. „Foto: Verein“."),
                },
                "alternativtext": {"type": "string", "maxLength": MAX_ALT},
                "bildunterschrift": {"type": "string", "maxLength": MAX_ALT},
            },
            ["adresse", "quelle"],
        ),
        run=_image_fetch,
        writes=True,
        scope=SCOPE_DRAFT,
    ),
    Tool(
        name="social_beitrag_entwerfen",
        title=gettext_lazy("Social-Media-Beitrag entwerfen"),
        description=gettext_lazy(
            "Legt einen Entwurf für Instagram oder Facebook an (Text und Bilder aus der "
            "Bilderverwaltung). Gepostet wird von Hand; HUBIplan veröffentlicht nichts bei Meta."
        ),
        schema=_schema(
            {
                "text": {"type": "string", "maxLength": MAX_SOCIAL},
                "bilder": {"type": "array", "items": NUMBER, "maxItems": 10},
                "kanal": {"type": "string", "enum": ["", "instagram", "facebook"]},
            },
            ["text"],
        ),
        run=_social_draft,
        writes=True,
        scope=SCOPE_DRAFT,
    ),
    Tool(
        name="social_entwuerfe",
        title=gettext_lazy("Social-Media-Entwürfe"),
        description=gettext_lazy("Listet die Entwürfe für Social-Media-Beiträge."),
        schema=_schema(),
        run=_social_list,
        scope=SCOPE_READ,
    ),
)
