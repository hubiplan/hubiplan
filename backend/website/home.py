"""Abschnitte der Startseite (Konzept webseite-baukasten G3, Ralf 10.11.2026).

Die Startseite besteht aus den festen Bausteinen (je einmal, ``HOME_SECTIONS``) und aus
eigenen Abschnitten, die sich mehrfach einsetzen lassen (Text, Text mit Bild, Banner,
Knopfleiste, Kacheln, Termin, Album-Auszug, Zitat, Ansprechpartner). Alle stehen in
``Website.home_sections`` und laufen damit über den Entwurf der Gestaltung (G2).

Jeder Eintrag: ``key``, ``on`` und die Gestaltung ``bg`` (Hintergrund), ``width``
(Breite) und ``column`` (Spalte im Design „Zeitung“). Eigene Abschnitte haben einen
Schlüssel ``c:<kennung>``, ihre Art ``kind`` und ihren Inhalt ``data``.
"""

from __future__ import annotations

import datetime
import re

from django.utils import timezone
from django.utils.translation import gettext

# Eigene Abschnitte: Art → Name in der Verwaltung
KINDS = {
    "text": "Text",
    "text_image": "Text mit Bild",
    "banner": "Banner",
    "buttons": "Knopfleiste",
    "tiles": "Kacheln",
    "event": "Hervorgehobener Termin",
    "album": "Album-Auszug",
    "quote": "Zitat",
    "contacts": "Ansprechpartner",
}
KIND_HINTS = {
    "text": "Überschrift und Text",
    "text_image": "Überschrift, Text und ein Bild daneben",
    "banner": "ein breites Bild, auf Wunsch mit einer Zeile darauf",
    "buttons": "ein bis drei Knöpfe zu Seiten, zum Kontakt oder nach außen",
    "tiles": "zwei bis sechs Kacheln mit Bild, Titel und Ziel",
    "event": "ein Termin groß mit „noch N Tage“; verschwindet danach",
    "album": "vier bis acht Bilder aus einem Album der Galerie",
    "quote": "ein kurzer Text mit Namen",
    "contacts": "ein bis vier Rollen mit Foto, Name und „Nachricht schreiben“",
}
# Nur auf Textseiten (G6): Titelbild, ein schmales Bild über der Überschrift, höchstens eins
PAGE_KINDS = {"cover": "Titelbild"}
PAGE_KIND_HINTS = {"cover": "ein schmales Bild über der Überschrift der Seite"}
ALL_KINDS = {**KINDS, **PAGE_KINDS}
# Welcher Bereich der Webseite eingeschaltet sein muss
KIND_NEEDS_BLOCK = {"event": "events", "album": "gallery"}

CUSTOM_KEY = re.compile(r"^c:[a-z0-9]{1,24}$")
MAX_CUSTOM = 30
BACKGROUNDS = ("none", "light")  # dazu ``p0`` … ``p9``: Farbe aus der Palette
PALETTE_BG = re.compile(r"^p[0-9]$")
WIDTHS = ("content", "text", "full")
COLUMNS = ("main", "side")
# Zeitung: diese Bausteine standen bisher fest in der rechten Spalte
SIDE_DEFAULT = {"events", "honors", "units", "event", "contacts", "quote"}

TITLE_MAX = 150
TEXT_MAX = 10000
SHORT_MAX = 500
LABEL_MAX = 60
URL_MAX = 500
EVENT_DAYS_AHEAD = 400


class Invalid(ValueError):
    pass


def is_custom(key: str) -> bool:
    return isinstance(key, str) and bool(CUSTOM_KEY.match(key))


def _layout(item: dict, key_or_kind: str) -> dict:
    """Gestaltung eines Eintrags: unbekannte Werte fallen auf den Standard zurück."""
    bg = item.get("bg")
    width = item.get("width")
    column = item.get("column")
    return {
        "bg": bg if bg in BACKGROUNDS or (isinstance(bg, str) and PALETTE_BG.match(bg)) else "none",
        "width": width if width in WIDTHS else "content",
        "column": column
        if column in COLUMNS
        else ("side" if key_or_kind in SIDE_DEFAULT else "main"),
    }


def normalize(value, builtin_keys, default_off, kinds=KINDS) -> list[dict]:
    """Gespeicherte Liste → vollständige Liste in Reihenfolge (neue Bausteine hinten)."""
    result, seen = [], set()
    for item in value or []:
        key = item.get("key") if isinstance(item, dict) else None
        if not isinstance(key, str) or key in seen:
            continue
        if key in builtin_keys:
            seen.add(key)
            result.append({"key": key, "on": bool(item.get("on", True)), **_layout(item, key)})
        elif is_custom(key) and item.get("kind") in kinds:
            seen.add(key)
            data = item.get("data")
            result.append(
                {
                    "key": key,
                    "kind": item["kind"],
                    "on": bool(item.get("on", True)),
                    **_layout(item, item["kind"]),
                    "data": data if isinstance(data, dict) else {},
                }
            )
    for key in builtin_keys:
        if key not in seen:
            result.append({"key": key, "on": key not in default_off, **_layout({}, key)})
    return result


# --- Prüfen beim Speichern ---


def _text(value, limit: int, label: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise Invalid(gettext("{x0}: bitte als Text angeben.").format(x0=label))
    value = value.strip()
    if len(value) > limit:
        raise Invalid(gettext("{x0}: höchstens {x1} Zeichen.").format(x0=label, x1=limit))
    return value


def _choice(value, choices, default):
    return value if value in choices else default


def _ref(value, known: set[int]) -> int | None:
    """Verweis auf ein Bild, Album, Termin oder eine Rolle; Gelöschtes fällt weg."""
    return (
        value if isinstance(value, int) and not isinstance(value, bool) and value in known else None
    )


def _target(value, refs: dict) -> dict | None:
    """Ziel eines Knopfs oder einer Kachel: Menüpunkt (Seite, Kontakt …), Termin oder Link."""
    if not isinstance(value, dict):
        return None
    page = value.get("page")
    if isinstance(page, str) and page:
        return {"page": page} if page in refs["pages"] else None
    event = _ref(value.get("event"), refs["events"])
    if event is not None:
        return {"event": event}
    url = value.get("url")
    if isinstance(url, str) and url.strip():
        url = url.strip()
        if len(url) > URL_MAX or not re.match(r"^https?://[^\s/]+\.[^\s]+$", url):
            raise Invalid(gettext("Bitte eine Adresse mit https:// angeben."))
        return {"url": url}
    return None


def _clean_data(kind: str, data: dict, refs: dict) -> dict:
    title = _text(data.get("title"), TITLE_MAX, gettext("Überschrift"))
    if kind == "text":
        return {"title": title, "text": _text(data.get("text"), TEXT_MAX, gettext("Text"))}
    if kind == "text_image":
        return {
            "title": title,
            "text": _text(data.get("text"), TEXT_MAX, gettext("Text")),
            "image": _ref(data.get("image"), refs["images"]),
            "side": _choice(data.get("side"), ("left", "right"), "right"),
            "size": _choice(data.get("size"), ("small", "half"), "half"),
        }
    if kind == "banner":
        return {
            "image": _ref(data.get("image"), refs["images"]),
            "line": _text(data.get("line"), TITLE_MAX, gettext("Zeile")),
            "height": _choice(data.get("height"), ("low", "high"), "low"),
        }
    if kind == "cover":
        return {"image": _ref(data.get("image"), refs["images"])}
    if kind == "buttons":
        items = data.get("buttons") if isinstance(data.get("buttons"), list) else []
        if len(items) > 3:
            raise Invalid(gettext("Höchstens drei Knöpfe."))
        buttons = []
        for b in items:
            b = b if isinstance(b, dict) else {}
            buttons.append(
                {
                    "label": _text(b.get("label"), LABEL_MAX, gettext("Beschriftung")),
                    "target": _target(b.get("target"), refs),
                }
            )
        return {
            "title": title,
            "buttons": buttons,
            "align": _choice(data.get("align"), ("left", "center", "right"), "left"),
        }
    if kind == "tiles":
        items = data.get("tiles") if isinstance(data.get("tiles"), list) else []
        if len(items) > 6:
            raise Invalid(gettext("Höchstens sechs Kacheln."))
        tiles = []
        for k in items:
            k = k if isinstance(k, dict) else {}
            tiles.append(
                {
                    "title": _text(k.get("title"), TITLE_MAX, gettext("Titel")),
                    "text": _text(k.get("text"), SHORT_MAX, gettext("Text")),
                    "image": _ref(k.get("image"), refs["images"]),
                    "target": _target(k.get("target"), refs),
                }
            )
        columns = data.get("columns")
        return {"title": title, "tiles": tiles, "columns": columns if columns in (2, 3) else 3}
    if kind == "event":
        return {"title": title, "event": _ref(data.get("event"), refs["events"])}
    if kind == "album":
        count = data.get("count")
        return {
            "title": title,
            "album": _ref(data.get("album"), refs["albums"]),
            "count": count if isinstance(count, int) and 4 <= count <= 8 else 4,
        }
    if kind == "quote":
        return {
            "text": _text(data.get("text"), SHORT_MAX * 2, gettext("Zitat")),
            "name": _text(data.get("name"), TITLE_MAX, gettext("Name")),
        }
    if kind == "contacts":
        items = data.get("roles") if isinstance(data.get("roles"), list) else []
        if len(items) > 4:
            raise Invalid(gettext("Höchstens vier Ansprechpartner."))
        roles = []
        for r in items:
            r = _ref(r, refs["roles"])
            if r is not None and r not in roles:
                roles.append(r)
        return {"title": title, "roles": roles}
    raise Invalid(gettext("Unbekannte Abschnittsart."))


def references(website) -> dict:
    """Was ein Abschnitt verwenden darf: Bilder, Alben, Termine, Rollen und Menüpunkte."""
    from events.models import Event

    from . import menu
    from .content_models import GalleryAlbum, WebsiteImage
    from .public import SiteView

    site = SiteView(website)
    return {
        "images": set(WebsiteImage.objects.filter(website=website).values_list("pk", flat=True)),
        "albums": set(GalleryAlbum.objects.filter(website=website).values_list("pk", flat=True)),
        "events": set(
            Event.objects.filter(
                organization=site.area, visibility=Event.Visibility.PUBLIC
            ).values_list("pk", flat=True)
        ),
        "roles": set(site.own_roles().filter(on_website=True).values_list("pk", flat=True)),
        "pages": {
            key
            for key, item in menu.items(website).items()
            if not item["heading"] and not key.startswith("link:")
        },
    }


def validate(value, website, builtin_keys, default_off, kinds=KINDS) -> list[dict]:
    """Prüft die Liste aus der Verwaltung; wirft Invalid mit einer lesbaren Meldung."""
    if not isinstance(value, list) or not all(
        isinstance(v, dict) and isinstance(v.get("key"), str) and isinstance(v.get("on"), bool)
        for v in value
    ):
        raise Invalid(gettext("Bausteine der Startseite bitte als Liste angeben."))
    custom = [v for v in value if v["key"] not in builtin_keys]
    for v in custom:
        if not is_custom(v["key"]) or v.get("kind") not in kinds:
            raise Invalid(gettext("Unbekannter Baustein: {x0}").format(x0=v["key"]))
        if v.get("data") is not None and not isinstance(v.get("data"), dict):
            raise Invalid(gettext("Unbekannter Baustein: {x0}").format(x0=v["key"]))
    if len(custom) > MAX_CUSTOM:
        raise Invalid(gettext("Höchstens {x0} eigene Abschnitte.").format(x0=MAX_CUSTOM))
    if sum(1 for v in custom if v.get("kind") == "cover") > 1:
        raise Invalid(gettext("Eine Seite hat höchstens ein Titelbild."))
    refs = references(website) if custom and website is not None else None
    result = normalize(value, builtin_keys, default_off, kinds)
    for item in result:
        if "kind" in item:
            if refs is None:
                raise Invalid(gettext("Unbekannter Baustein: {x0}").format(x0=item["key"]))
            item["data"] = _clean_data(item["kind"], item["data"], refs)
    return result


# --- Öffentliche Schnittstelle ---


def image_ids(sections: list[dict]) -> set[int]:
    """Bilder eingeschalteter Abschnitte (dürfen öffentlich ausgeliefert werden)."""
    ids = set()
    for s in sections:
        if not s.get("on") or "kind" not in s:
            continue
        data = s["data"]
        if isinstance(data.get("image"), int):
            ids.add(data["image"])
        for tile in data.get("tiles") or []:
            if isinstance(tile, dict) and isinstance(tile.get("image"), int):
                ids.add(tile["image"])
    return ids


def public(site, home_keys: list[str], event_entry) -> list[dict]:
    """Eingeschaltete Abschnitte mit Inhalt für die Webseite, in Reihenfolge.

    Feste Bausteine erscheinen nur, wenn sie in ``home_keys`` stehen (an und Bereich an);
    eigene Abschnitte ohne Inhalt fallen weg. ``event_entry`` macht aus einem Einzeltermin
    die Angaben wie unter ``events/``."""
    from .models import normalize_home_sections

    return resolve(site, normalize_home_sections(site.site.home_sections), home_keys, event_entry)


def resolve(site, sections: list[dict], builtin_keys, event_entry) -> list[dict]:
    """Abschnitte (Startseite oder Textseite) mit aufgelöstem Inhalt für die Webseite."""
    from . import menu

    images = _images(site, image_ids(sections))
    known = None
    result = []
    for s in sections:
        layout = {"key": s["key"], "bg": s["bg"], "width": s["width"], "column": s["column"]}
        if "kind" not in s:
            if s["key"] in builtin_keys:
                result.append({**layout, "kind": s["key"]})
            continue
        needs = KIND_NEEDS_BLOCK.get(s["kind"])
        if not s["on"] or (needs and not site.site.block_on(needs)):
            continue
        if known is None:
            known = menu.items(site.site, public_site=site)
        content = _content(site, s["kind"], s["data"], images, known, event_entry)
        if content is not None:
            result.append({**layout, "kind": s["kind"], **content})
    return result


# --- Textseiten (G4) ---


# Der bisherige Inhalt einer Textseite (Bild oben und Text) ist ein fester Abschnitt; ohne
# eigene Abschnitte sieht die Seite aus wie vorher.
def skeleton(sections) -> list[tuple]:
    """Aufbau der Abschnitte ohne Inhalt: Reihenfolge, Art, an/aus, Aussehen (F7).
    Wer nur Inhalte bearbeiten darf, darf daran nichts ändern."""
    return [
        (s.get("key"), s.get("kind"), s.get("on"), s.get("bg"), s.get("width"), s.get("column"))
        for s in sections
        if isinstance(s, dict)
    ]


PAGE_BUILTINS = ("body",)


def normalize_page(value) -> list[dict]:
    return normalize(value, PAGE_BUILTINS, set(), ALL_KINDS)


def validate_page(value, website) -> list[dict]:
    return validate(value, website, PAGE_BUILTINS, set(), ALL_KINDS)


def has_custom(sections) -> bool:
    return any(isinstance(s, dict) and "kind" in s for s in normalize_page(sections))


# --- Datenumzug: Nummern im Inhalt auf die des neuen Servers umstellen ---

REF_TABLES = {
    "image": "website.websiteimage",
    "album": "website.galleryalbum",
    "event": "events.event",
}


def remap(value, get) -> list:
    """Verweise in eigenen Abschnitten umstellen; ``get(tabelle, alt)`` liefert die neue
    Nummer oder None (dann fällt der Verweis weg, der Abschnitt bleibt)."""
    if not isinstance(value, list):
        return value

    def one(table, old):
        try:
            return get(table, old) if isinstance(old, int) else None
        except (TypeError, ValueError):
            return None

    def target(t):
        if isinstance(t, dict) and "event" in t:
            new = one("events.event", t["event"])
            return {"event": new} if new is not None else None
        return t

    result = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("data"), dict):
            result.append(item)
            continue
        data = dict(item["data"])
        for field, table in REF_TABLES.items():
            if field in data:
                data[field] = one(table, data[field])
        if isinstance(data.get("roles"), list):
            data["roles"] = [
                r for r in (one("access.role", r) for r in data["roles"]) if r is not None
            ]
        for list_field in ("buttons", "tiles"):
            if isinstance(data.get(list_field), list):
                data[list_field] = [
                    {
                        **x,
                        **(
                            {"image": one("website.websiteimage", x.get("image"))}
                            if "image" in x
                            else {}
                        ),
                        "target": target(x.get("target")),
                    }
                    if isinstance(x, dict)
                    else x
                    for x in data[list_field]
                ]
        result.append({**item, "data": data})
    return result


def _images(site, ids: set[int]) -> dict[int, dict]:
    from .content_models import WebsiteImage

    if not ids:
        return {}
    return {i.pk: site.image(i) for i in WebsiteImage.objects.filter(website=site.site, pk__in=ids)}


def _public_target(site, target, known, event_entry) -> dict | None:
    from . import menu

    if not isinstance(target, dict):
        return None
    if "url" in target:
        return {"key": "link", "url": target["url"]}
    if "page" in target:
        return menu.public_target(site, target["page"], known)
    if "event" in target:
        if not site.site.block_on("events"):
            return None
        return {"key": "events"}
    return None


def next_occurrence(site, event_pk: int):
    """Nächster Einzeltermin eines Termins (noch nicht vorbei), sonst None."""
    from events.models import Event
    from events.recurrence import occurrences

    event = (
        Event.objects.filter(
            pk=event_pk, organization=site.area, visibility=Event.Visibility.PUBLIC
        )
        .select_related("category", "department", "organization")
        .first()
    )
    if event is None or event.source_stale:
        return None
    now = timezone.now()
    found = occurrences([event], now, now + datetime.timedelta(days=EVENT_DAYS_AHEAD))
    return found[0] if found else None


def _content(site, kind, data, images, known, event_entry) -> dict | None:
    title = data.get("title") or ""
    if kind == "text":
        return (
            {"title": title, "text": data.get("text") or ""} if title or data.get("text") else None
        )
    if kind == "text_image":
        image = images.get(data.get("image"))
        if not (title or data.get("text") or image):
            return None
        return {
            "title": title,
            "text": data.get("text") or "",
            "image": image,
            "side": data.get("side", "right"),
            "size": data.get("size", "half"),
        }
    if kind == "cover":
        image = images.get(data.get("image"))
        return {"image": image} if image is not None else None
    if kind == "banner":
        image = images.get(data.get("image"))
        if image is None:
            return None
        return {"image": image, "line": data.get("line") or "", "height": data.get("height", "low")}
    if kind == "buttons":
        buttons = []
        for b in data.get("buttons") or []:
            target = _public_target(site, b.get("target"), known, event_entry)
            if b.get("label") and target:
                buttons.append({"label": b["label"], "target": target})
        if not buttons:
            return None
        return {"title": title, "buttons": buttons, "align": data.get("align", "left")}
    if kind == "tiles":
        tiles = [
            {
                "title": k.get("title") or "",
                "text": k.get("text") or "",
                "image": images.get(k.get("image")),
                "target": _public_target(site, k.get("target"), known, event_entry),
            }
            for k in data.get("tiles") or []
            if k.get("title")
        ]
        if not tiles:
            return None
        return {"title": title, "tiles": tiles, "columns": data.get("columns", 3)}
    if kind == "event":
        if not data.get("event"):
            return None
        occurrence = next_occurrence(site, data["event"])
        if occurrence is None:
            return None
        return {"title": title, "event": event_entry(site, occurrence)}
    if kind == "album":
        return _album(site, title, data)
    if kind == "quote":
        if not data.get("text"):
            return None
        return {"text": data["text"], "name": data.get("name") or ""}
    if kind == "contacts":
        roles = site.role_cards(data.get("roles") or [])
        return {"title": title, "roles": roles} if roles else None
    return None


def _album(site, title, data) -> dict | None:
    from . import gallery

    if not data.get("album"):
        return None
    album = gallery.visible_albums(site.site).filter(pk=data["album"]).first()
    if album is None:
        return None
    items = gallery.sort_items(list(album.items.select_related("image")), album.image_order)[
        : data.get("count", 4)
    ]
    images = [gallery._image(site.image, i.image, captions=False) for i in items]
    images = [i for i in images if i]
    if not images:
        return None
    return {
        "title": title or album.title,
        "album": {"slug": album.slug, "title": album.title},
        "images": images,
    }
