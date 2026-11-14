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
from django.utils.translation import gettext, gettext_noop

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
    # Weitere Arten (Ralf 10.11.2026 „alle 9“)
    "faq": "Häufige Fragen",
    "partners": "Partner und Sponsoren",
    "directions": "Anfahrt",
    "event_list": "Termine einer Art",
    "document": "Dokument zum Herunterladen",
    "video": "Video als Link",
    "chronicle": "Auszug aus der Chronik",
    "facts": "Zahlen auf einen Blick",
    "divider": "Trenner",
    # Ralf 14.11.2026: laufender Zähler bis zu einem Termin oder Zeitpunkt
    "countdown": "Countdown",
    # Ralf 14.11.2026: weitere Arten (Inhalte ohne Datenbezug)
    "join": "Mitglied werden",
    "donation": "Spendenaufruf",
    "hours": "Öffnungs- und Trainingszeiten",
    "columns": "Zwei Spalten",
    "table": "Tabelle",
    "timeline": "Zeitstrahl",
    "program": "Festprogramm",
    "callout": "Hinweis-Kasten",
    "accordion": "Aufklappbare Abschnitte",
    "images": "Bilder",
    "downloads": "Download-Liste",
    # Ralf 14.11.2026: weitere Arten mit Daten aus HUBIplan
    "unit_honors": "Majestäten einer Untereinheit",
    "competition": "Ergebnisse eines Wettbewerbs",
    "albums": "Galerie-Übersicht",
    "posts": "Neueste Beiträge",
    "app": "Mitgliederbereich und App",
    "live_facts": "Zahlen aus HUBIplan",
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
    "faq": "Fragen mit Antworten zum Aufklappen",
    "partners": "Logos mit Link, z. B. Unterstützer und Sponsoren",
    "directions": "Anschrift eines Orts mit „Route planen“",
    "event_list": "die nächsten Termine einer Kategorie",
    "document": "eine Datei aus Webseite › Dokumente als Knopf",
    "video": "Vorschaubild mit Link zum Video, ohne Einbettung",
    "chronicle": "die neuesten Einträge der Zeitleiste",
    "facts": "zwei bis sechs Zahlen mit kurzem Text",
    "divider": "Linie oder Abstand zwischen Abschnitten",
    "countdown": "Tage, Stunden, Minuten und Sekunden bis zu einem Termin oder Zeitpunkt",
    "join": "kurzer Werbetext mit Knopf zum Online-Mitgliedsantrag",
    "donation": "Spendenzweck, Bankverbindung und auf Wunsch ein Fortschrittsbalken",
    "hours": "Wochentage mit Uhrzeiten, z. B. für Schießstand oder Probe",
    "columns": "zwei Textblöcke nebeneinander",
    "table": "eine einfache Tabelle mit Kopfzeile",
    "timeline": "eigene Stationen mit Zeitangabe und Text",
    "program": "Ablauf eines Fests mit Tagen und Uhrzeiten",
    "callout": "farbiger Kasten für Info, Achtung oder Erfolg",
    "accordion": "Überschriften mit Text zum Aufklappen",
    "images": "zwei bis acht eigene Bilder mit Bildunterschrift",
    "downloads": "mehrere Dateien aus Webseite › Dokumente als Liste",
    "unit_honors": "die aktuellen Majestäten einer Untereinheit",
    "competition": "Sieger und Stand eines bestimmten Wettbewerbs",
    "albums": "die ersten Alben der Galerie als Kacheln",
    "posts": "die neuesten Beiträge aus Instagram und Facebook",
    "app": "Knopf zum Mitgliederbereich, QR-Code und Hinweis auf die App",
    "live_facts": "Mitgliederzahl, Jahre seit der Gründung und Untereinheiten, immer aktuell",
}
# Nur auf Textseiten (G6): Titelbild, ein schmales Bild über der Überschrift, höchstens eins
PAGE_KINDS = {"cover": "Titelbild"}
PAGE_KIND_HINTS = {"cover": "ein schmales Bild über der Überschrift der Seite"}
ALL_KINDS = {**KINDS, **PAGE_KINDS}
# Welcher Bereich der Webseite eingeschaltet sein muss
KIND_NEEDS_BLOCK = {
    "event": "events",
    "album": "gallery",
    "event_list": "events",
    "chronicle": "history",
    "join": "join",
    "unit_honors": "honors",
    "albums": "gallery",
    "posts": "posts",
}

CUSTOM_KEY = re.compile(r"^c:[a-z0-9]{1,24}$")
MAX_CUSTOM = 30
BACKGROUNDS = ("none", "light")  # dazu ``p0`` … ``p9``: Farbe aus der Palette
PALETTE_BG = re.compile(r"^p[0-9]$")
# Verlauf aus Einstellungen › Erscheinungsbild als Hintergrund (Ralf 10.11.2026)
GRADIENT_BG = re.compile(r"^g[01]$")
WIDTHS = ("content", "text", "full")
COLUMNS = ("main", "side")
# Zeitung: diese Bausteine standen bisher fest in der rechten Spalte
SIDE_DEFAULT = {
    "events",
    "honors",
    "units",
    "event",
    "contacts",
    "quote",
    "directions",
    "event_list",
    "document",
    "countdown",
    "hours",
    "downloads",
    "join",
    "app",
    "unit_honors",
}

# Zahlen aus HUBIplan (nur Summen, keine Personendaten) → Vorgabetext auf der Webseite
LIVE_FACTS = {
    "members": gettext_noop("Mitglieder"),
    "years": gettext_noop("Jahre Vereinsgeschichte"),
    "units": gettext_noop("Untereinheiten"),
}
APP_STORE_URL = "https://play.google.com/store/apps/details?id=de.hubiplan.app"

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
        "bg": bg
        if bg in BACKGROUNDS
        or (isinstance(bg, str) and (PALETTE_BG.match(bg) or GRADIENT_BG.match(bg)))
        else "none",
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


LOCAL_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")


def _local_time(value) -> str:
    """Zeitpunkt als Ortszeit „JJJJ-MM-TTTHH:MM“ (wie ein datetime-local-Feld), leer erlaubt."""
    if value in (None, ""):
        return ""
    if isinstance(value, str) and LOCAL_TIME.match(value[:16]):
        try:
            datetime.datetime.strptime(value[:16], "%Y-%m-%dT%H:%M")
            return value[:16]
        except ValueError:
            pass
    raise Invalid(gettext("Zeitpunkt bitte als Datum mit Uhrzeit angeben."))


def _iban(value) -> str:
    """IBAN ohne Leerzeichen, in Großbuchstaben; leer erlaubt."""
    if value in (None, ""):
        return ""
    iban = re.sub(r"\s", "", value).upper() if isinstance(value, str) else ""
    if not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$", iban):
        raise Invalid(gettext("Bitte eine gültige IBAN angeben."))
    return iban


def _amount(value) -> int | None:
    """Betrag in ganzen Euro (0 bis 10 Millionen) oder leer."""
    if value in (None, ""):
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or not 0 <= value <= 10**7:
        raise Invalid(gettext("Beträge bitte in ganzen Euro angeben."))
    return int(value)


def _items(data: dict, limit: int, message: str) -> list[dict]:
    """Einträge einer Liste (Fragen, Partner, Zahlen); höchstens ``limit``."""
    items = data.get("items") if isinstance(data.get("items"), list) else []
    if len(items) > limit:
        raise Invalid(message)
    return [i if isinstance(i, dict) else {} for i in items]


def _url(value) -> str:
    """Adresse nach außen (https://…) oder leer."""
    if not isinstance(value, str) or not value.strip() or value.strip() == "https://":
        return ""
    url = value.strip()
    if len(url) > URL_MAX or not re.match(r"^https?://[^\s/]+\.[^\s]+$", url):
        raise Invalid(gettext("Bitte eine Adresse mit https:// angeben."))
    return url


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
    if kind == "faq":
        items = _items(data, 12, gettext("Höchstens zwölf Fragen."))
        return {
            "title": title,
            "items": [
                {
                    "question": _text(i.get("question"), TITLE_MAX, gettext("Frage")),
                    "answer": _text(i.get("answer"), TEXT_MAX // 5, gettext("Antwort")),
                }
                for i in items
            ],
        }
    if kind == "partners":
        items = _items(data, 12, gettext("Höchstens zwölf Partner."))
        return {
            "title": title,
            "items": [
                {
                    "name": _text(i.get("name"), LABEL_MAX * 2, gettext("Name")),
                    "image": _ref(i.get("image"), refs["images"]),
                    "url": _url(i.get("url")),
                }
                for i in items
            ],
        }
    if kind == "directions":
        return {
            "title": title,
            "place": _ref(data.get("place"), refs["places"]),
            "text": _text(data.get("text"), SHORT_MAX * 2, gettext("Text")),
        }
    if kind == "event_list":
        count = data.get("count")
        return {
            "title": title,
            "category": _ref(data.get("category"), refs["categories"]),
            "count": count if isinstance(count, int) and 2 <= count <= 10 else 4,
        }
    if kind == "document":
        return {
            "title": title,
            "document": _ref(data.get("document"), refs["documents"]),
            "label": _text(data.get("label"), LABEL_MAX, gettext("Beschriftung")),
        }
    if kind == "video":
        return {
            "title": title,
            "url": _url(data.get("url")),
            "image": _ref(data.get("image"), refs["images"]),
            "text": _text(data.get("text"), SHORT_MAX, gettext("Text")),
        }
    if kind == "chronicle":
        count = data.get("count")
        return {"title": title, "count": count if isinstance(count, int) and 2 <= count <= 6 else 3}
    if kind == "facts":
        items = _items(data, 6, gettext("Höchstens sechs Zahlen."))
        return {
            "title": title,
            "items": [
                {
                    "value": _text(i.get("value"), 20, gettext("Zahl")),
                    "label": _text(i.get("label"), LABEL_MAX, gettext("Text")),
                }
                for i in items
            ],
        }
    if kind == "divider":
        return {
            "style": _choice(data.get("style"), ("line", "space"), "line"),
            "size": _choice(data.get("size"), ("small", "large"), "small"),
        }
    if kind == "countdown":
        mode = _choice(data.get("mode"), ("event", "date"), "event")
        return {
            "title": title,
            "mode": mode,
            "event": _ref(data.get("event"), refs["events"]) if mode == "event" else None,
            "at": _local_time(data.get("at")) if mode == "date" else "",
            "text": _text(data.get("text"), SHORT_MAX, gettext("Text")),
            "after": _choice(data.get("after"), ("hide", "text"), "hide"),
            "after_text": _text(data.get("after_text"), SHORT_MAX, gettext("Text nach Ablauf")),
        }
    if kind == "join":
        return {
            "title": title,
            "text": _text(data.get("text"), TEXT_MAX // 5, gettext("Text")),
            "label": _text(data.get("label"), LABEL_MAX, gettext("Beschriftung")),
        }
    if kind == "donation":
        return {
            "title": title,
            "text": _text(data.get("text"), TEXT_MAX // 5, gettext("Text")),
            "holder": _text(data.get("holder"), LABEL_MAX * 2, gettext("Kontoinhaber")),
            "iban": _iban(data.get("iban")),
            "bic": _text(data.get("bic"), 11, gettext("BIC")),
            "purpose": _text(data.get("purpose"), LABEL_MAX * 2, gettext("Verwendungszweck")),
            "goal": _amount(data.get("goal")),
            "raised": _amount(data.get("raised")),
            "label": _text(data.get("label"), LABEL_MAX, gettext("Beschriftung")),
            "url": _url(data.get("url")),
        }
    if kind == "hours":
        items = _items(data, 14, gettext("Höchstens 14 Zeilen."))
        return {
            "title": title,
            "items": [
                {
                    "day": _text(i.get("day"), LABEL_MAX, gettext("Tag")),
                    "time": _text(i.get("time"), LABEL_MAX, gettext("Uhrzeit")),
                    "note": _text(i.get("note"), LABEL_MAX * 2, gettext("Hinweis")),
                }
                for i in items
            ],
            "text": _text(data.get("text"), SHORT_MAX, gettext("Text")),
        }
    if kind == "columns":
        items = _items(data, 2, gettext("Höchstens zwei Spalten."))
        items += [{}] * (2 - len(items))
        return {
            "title": title,
            "items": [
                {
                    "title": _text(i.get("title"), TITLE_MAX, gettext("Überschrift")),
                    "text": _text(i.get("text"), TEXT_MAX // 2, gettext("Text")),
                }
                for i in items
            ],
        }
    if kind == "table":
        head = data.get("head") if isinstance(data.get("head"), list) else []
        if not 1 <= len(head) <= 6:
            raise Invalid(gettext("Eine Tabelle hat eine bis sechs Spalten."))
        rows = data.get("rows") if isinstance(data.get("rows"), list) else []
        if len(rows) > 40:
            raise Invalid(gettext("Höchstens 40 Zeilen."))
        cell = gettext("Zelle")
        return {
            "title": title,
            "head": [_text(h, LABEL_MAX, cell) for h in head],
            "rows": [
                [
                    _text(r[c] if isinstance(r, list) and c < len(r) else "", LABEL_MAX * 2, cell)
                    for c in range(len(head))
                ]
                for r in rows
            ],
            "text": _text(data.get("text"), SHORT_MAX, gettext("Text")),
        }
    if kind == "timeline":
        items = _items(data, 12, gettext("Höchstens zwölf Stationen."))
        return {
            "title": title,
            "items": [
                {
                    "when": _text(i.get("when"), LABEL_MAX, gettext("Zeitangabe")),
                    "title": _text(i.get("title"), TITLE_MAX, gettext("Titel")),
                    "text": _text(i.get("text"), SHORT_MAX, gettext("Text")),
                }
                for i in items
            ],
        }
    if kind == "program":
        items = _items(data, 40, gettext("Höchstens 40 Programmpunkte."))
        return {
            "title": title,
            "items": [
                {
                    "day": _text(i.get("day"), LABEL_MAX, gettext("Tag")),
                    "time": _text(i.get("time"), 20, gettext("Uhrzeit")),
                    "text": _text(i.get("text"), SHORT_MAX, gettext("Programmpunkt")),
                }
                for i in items
            ],
            "text": _text(data.get("text"), SHORT_MAX, gettext("Text")),
        }
    if kind == "callout":
        return {
            "title": title,
            "text": _text(data.get("text"), TEXT_MAX // 5, gettext("Text")),
            "style": _choice(data.get("style"), ("info", "warning", "success"), "info"),
        }
    if kind == "accordion":
        items = _items(data, 12, gettext("Höchstens zwölf Abschnitte."))
        return {
            "title": title,
            "items": [
                {
                    "title": _text(i.get("title"), TITLE_MAX, gettext("Überschrift")),
                    "text": _text(i.get("text"), TEXT_MAX // 2, gettext("Text")),
                }
                for i in items
            ],
        }
    if kind == "images":
        items = _items(data, 8, gettext("Höchstens acht Bilder."))
        columns = data.get("columns")
        return {
            "title": title,
            "items": [
                {
                    "image": _ref(i.get("image"), refs["images"]),
                    "caption": _text(i.get("caption"), SHORT_MAX // 2, gettext("Bildunterschrift")),
                }
                for i in items
            ],
            "columns": columns if columns in (2, 3, 4) else 3,
        }
    if kind == "downloads":
        docs = data.get("documents") if isinstance(data.get("documents"), list) else []
        if len(docs) > 10:
            raise Invalid(gettext("Höchstens zehn Dokumente."))
        result = []
        for d in docs:
            d = _ref(d, refs["documents"])
            if d is not None and d not in result:
                result.append(d)
        return {"title": title, "documents": result}
    if kind == "unit_honors":
        return {"title": title, "unit": _ref(data.get("unit"), refs["units"])}
    if kind == "competition":
        return {"title": title, "competition": _ref(data.get("competition"), refs["competitions"])}
    if kind == "albums":
        count = data.get("count")
        return {"title": title, "count": count if isinstance(count, int) and 2 <= count <= 8 else 4}
    if kind == "posts":
        count = data.get("count")
        return {
            "title": title,
            "count": count if isinstance(count, int) and 1 <= count <= 6 else 3,
            "channel": _choice(data.get("channel"), ("all", "instagram", "facebook"), "all"),
        }
    if kind == "app":
        return {
            "title": title,
            "text": _text(data.get("text"), TEXT_MAX // 5, gettext("Text")),
            "qr": data.get("qr") is not False,
            "store": data.get("store") is not False,
        }
    if kind == "live_facts":
        items = data.get("items") if isinstance(data.get("items"), list) else []
        if len(items) > len(LIVE_FACTS):
            raise Invalid(gettext("Jede Zahl nur einmal."))
        result = []
        for i in items:
            i = i if isinstance(i, dict) else {}
            fact = i.get("fact")
            if fact not in LIVE_FACTS or any(r["fact"] == fact for r in result):
                raise Invalid(gettext("Unbekannte Zahl."))
            result.append(
                {"fact": fact, "label": _text(i.get("label"), LABEL_MAX, gettext("Text"))}
            )
        return {"title": title, "items": result}
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
    from events.models import Event, EventCategory
    from places.models import Place

    from . import menu
    from .content_models import GalleryAlbum, WebsiteDocument, WebsiteImage
    from .public import SiteView

    site = SiteView(website)
    return {
        "places": set(
            Place.objects.filter(organization=site.area, is_active=True).values_list(
                "pk", flat=True
            )
        ),
        "categories": set(
            EventCategory.objects.filter(organization=site.area, is_active=True).values_list(
                "pk", flat=True
            )
        ),
        "documents": set(
            WebsiteDocument.objects.filter(website=website, published=True).values_list(
                "pk", flat=True
            )
        ),
        "images": set(WebsiteImage.objects.filter(website=website).values_list("pk", flat=True)),
        "albums": set(GalleryAlbum.objects.filter(website=website).values_list("pk", flat=True)),
        "events": set(
            Event.objects.filter(
                organization=site.area, visibility=Event.Visibility.PUBLIC
            ).values_list("pk", flat=True)
        ),
        "roles": set(site.own_roles().filter(on_website=True).values_list("pk", flat=True)),
        "units": {u.pk for u in site.units},
        "competitions": set(competition_choices(site).values_list("pk", flat=True)),
        "pages": {
            key
            for key, item in menu.items(website).items()
            if not item["heading"] and not key.startswith("link:")
        },
    }


def competition_choices(site):
    """Wettbewerbe, die eine Webseite zeigen darf (ohne „nicht auf der Webseite“)."""
    from competitions.models import Competition

    return Competition.objects.filter(organization=site.org).exclude(
        website=Competition.Website.OFF
    )


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
        for tile in [*(data.get("tiles") or []), *(data.get("items") or [])]:
            if isinstance(tile, dict) and isinstance(tile.get("image"), int):
                ids.add(tile["image"])
    return ids


def text_image_keys(sections: list[dict]) -> set[str]:
    """Schlüssel der Bilder, die als ``![…](bild:<key>)`` im Text eingeschalteter Abschnitte
    stehen (#415). Sie dürfen wie Bilder mit eigener Bildnummer öffentlich ausgeliefert werden."""
    from .content import _IMAGE_KEY

    keys: set[str] = set()

    def walk(value):
        if isinstance(value, str):
            if "bild:" in value:
                keys.update(_IMAGE_KEY.findall(value))
        elif isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    for s in sections:
        if s.get("on") and "kind" in s:
            walk(s.get("data"))
    return keys


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
    "place": "places.place",
    "category": "events.eventcategory",
    "document": "website.websitedocument",
    "unit": "organizations.department",
    "competition": "competitions.competition",
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
        if isinstance(data.get("documents"), list):
            data["documents"] = [
                d
                for d in (one("website.websitedocument", d) for d in data["documents"])
                if d is not None
            ]
        if isinstance(data.get("roles"), list):
            data["roles"] = [
                r for r in (one("access.role", r) for r in data["roles"]) if r is not None
            ]
        for list_field in ("buttons", "tiles", "items"):
            if isinstance(data.get(list_field), list):
                data[list_field] = [
                    {
                        **x,
                        **(
                            {"image": one("website.websiteimage", x.get("image"))}
                            if "image" in x
                            else {}
                        ),
                        **({"target": target(x.get("target"))} if "target" in x else {}),
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
    if kind == "faq":
        items = [
            {"question": i["question"], "answer": i.get("answer") or ""}
            for i in data.get("items") or []
            if isinstance(i, dict) and i.get("question")
        ]
        return {"title": title, "items": items} if items else None
    if kind == "partners":
        items = [
            {"name": i["name"], "image": images.get(i.get("image")), "url": i.get("url") or ""}
            for i in data.get("items") or []
            if isinstance(i, dict) and i.get("name")
        ]
        return {"title": title, "items": items} if items else None
    if kind == "directions":
        return _directions(site, title, data)
    if kind == "event_list":
        return _event_list(site, title, data, event_entry)
    if kind == "document":
        return _document(site, title, data)
    if kind == "video":
        if not data.get("url"):
            return None
        return {
            "title": title,
            "url": data["url"],
            "image": images.get(data.get("image")),
            "text": data.get("text") or "",
        }
    if kind == "chronicle":
        return _chronicle(site, title, data)
    if kind == "facts":
        items = [
            {"value": i["value"], "label": i.get("label") or ""}
            for i in data.get("items") or []
            if isinstance(i, dict) and i.get("value")
        ]
        return {"title": title, "items": items} if items else None
    if kind == "divider":
        return {"style": data.get("style", "line"), "size": data.get("size", "small")}
    if kind == "countdown":
        return _countdown(site, title, data)
    if kind == "join":
        target = _public_target(site, {"page": "join"}, known, event_entry)
        if target is None:
            return None
        return {
            "title": title,
            "text": data.get("text") or "",
            "label": data.get("label") or "",
            "target": target,
        }
    if kind == "donation":
        if not (title or data.get("text") or data.get("iban") or data.get("url")):
            return None
        goal = data.get("goal")
        raised = data.get("raised")
        return {
            "title": title,
            "text": data.get("text") or "",
            "holder": data.get("holder") or "",
            "iban": data.get("iban") or "",
            "bic": data.get("bic") or "",
            "purpose": data.get("purpose") or "",
            "goal": goal or None,
            "raised": raised if goal else None,
            "percent": min(100, round(100 * (raised or 0) / goal)) if goal else None,
            "label": data.get("label") or "",
            "url": data.get("url") or "",
        }
    if kind == "hours":
        items = [
            {"day": i["day"], "time": i.get("time") or "", "note": i.get("note") or ""}
            for i in data.get("items") or []
            if isinstance(i, dict) and i.get("day")
        ]
        return {"title": title, "items": items, "text": data.get("text") or ""} if items else None
    if kind in ("columns", "accordion"):
        items = [
            {"title": i.get("title") or "", "text": i.get("text") or ""}
            for i in data.get("items") or []
            if isinstance(i, dict)
            and (i.get("title") or i.get("text"))
            and (kind == "columns" or i.get("title"))
        ]
        return {"title": title, "items": items} if items else None
    if kind == "table":
        rows = [r for r in data.get("rows") or [] if isinstance(r, list) and any(r)]
        if not rows:
            return None
        return {
            "title": title,
            "head": data.get("head") or [],
            "rows": rows,
            "text": data.get("text") or "",
        }
    if kind == "timeline":
        items = [
            {"when": i.get("when") or "", "title": i["title"], "text": i.get("text") or ""}
            for i in data.get("items") or []
            if isinstance(i, dict) and i.get("title")
        ]
        return {"title": title, "items": items} if items else None
    if kind == "program":
        days: list[dict] = []
        for i in data.get("items") or []:
            if not isinstance(i, dict) or not i.get("text"):
                continue
            day = i.get("day") or ""
            if not days or days[-1]["day"] != day:
                days.append({"day": day, "items": []})
            days[-1]["items"].append({"time": i.get("time") or "", "text": i["text"]})
        if not days:
            return None
        return {"title": title, "days": days, "text": data.get("text") or ""}
    if kind == "callout":
        if not (title or data.get("text")):
            return None
        return {"title": title, "text": data.get("text") or "", "style": data.get("style", "info")}
    if kind == "images":
        items = [
            {"image": images[i["image"]], "caption": i.get("caption") or ""}
            for i in data.get("items") or []
            if isinstance(i, dict) and images.get(i.get("image"))
        ]
        if not items:
            return None
        return {"title": title, "items": items, "columns": data.get("columns", 3)}
    if kind == "downloads":
        return _downloads(site, title, data)
    if kind == "unit_honors":
        return _unit_honors(site, title, data)
    if kind == "competition":
        return _competition(site, title, data)
    if kind == "albums":
        from . import gallery

        albums = gallery.public_list(site.site, site.image)[: data.get("count", 4)]
        return {"title": title, "albums": albums} if albums else None
    if kind == "posts":
        if not site.site.block_on("posts"):
            return None
        channel = data.get("channel", "all")
        posts = site.posts(None if channel == "all" else channel, None, data.get("count", 3))
        return {"title": title, "posts": posts, "channel": channel} if posts else None
    if kind == "app":
        from organizations.addresses import base_url

        return {
            "title": title,
            "text": data.get("text") or "",
            "login_url": f"{base_url(site.org)}/anmelden",
            "qr": data.get("qr", True),
            "store_url": APP_STORE_URL if data.get("store", True) else "",
        }
    if kind == "live_facts":
        values = _live_values(site, {i.get("fact") for i in data.get("items") or []})
        items = [
            {
                "value": str(values[i["fact"]]),
                "label": i.get("label")
                or (
                    site.org.department_label_plural
                    if i["fact"] == "units" and site.org.department_label_plural
                    else gettext(LIVE_FACTS[i["fact"]])
                ),
            }
            for i in data.get("items") or []
            if values.get(i.get("fact")) is not None
        ]
        return {"title": title, "items": items} if items else None
    return None


def _live_values(site, wanted: set) -> dict:
    """Summen für „Zahlen aus HUBIplan“; keine Angaben zu einzelnen Personen."""
    from django.db.models import Q

    from members.models import Membership

    result: dict = {}
    if "members" in wanted:
        on = timezone.localdate()
        result["members"] = (
            Membership.objects.filter(
                organization=site.area,
                periods__entry_date__lte=on,
            )
            .filter(Q(periods__exit_date__isnull=True) | Q(periods__exit_date__gte=on))
            .distinct()
            .count()
        ) or None
    if "years" in wanted:
        year = getattr(site.org, "founding_year", None)
        result["years"] = timezone.localdate().year - year if year else None
    if "units" in wanted:
        result["units"] = len(site.units) or None
    return result


def _unit_honors(site, title, data) -> dict | None:
    unit = next((u for u in site.units if u.pk == data.get("unit")), None)
    if unit is None:
        return None
    honors = site.honors(unit)
    if not honors:
        return None
    return {
        "title": title,
        "unit": {"name": unit.name, "slug": site.unit_slugs.get(unit.pk, "")},
        "honors": honors,
    }


def _competition(site, title, data) -> dict | None:
    from . import results

    comp = next((c for c in results.published(site) if c.pk == data.get("competition")), None)
    if comp is None:
        return None
    entry = results.home_entry(site, comp)
    return {"title": title, "competition": entry}


def _downloads(site, title, data) -> dict | None:
    from . import documents
    from .content_models import WebsiteDocument

    ids = [d for d in data.get("documents") or [] if isinstance(d, int)]
    if not ids:
        return None
    found = {d.pk: d for d in WebsiteDocument.objects.filter(pk__in=ids, website=site.site)}
    items = []
    for pk in ids:
        doc = found.get(pk)
        if doc is None or documents.find(site, doc.key) is None:
            continue
        items.append(
            {
                "label": doc.title,
                "url": site.url(f"files/{doc.key}/"),
                "file_type": "pdf" if doc.content_type == "application/pdf" else "image",
                "size": doc.size,
            }
        )
    return {"title": title, "items": items} if items else None


def _countdown(site, title, data) -> dict | None:
    """Ziel als Zeitpunkt mit Zeitzone; die Webseite zählt im Browser weiter herunter.
    Nach Ablauf (auch wenn der Termin begonnen hat oder nicht mehr öffentlich ist)
    verschwindet der Abschnitt, außer es ist ein Text dafür gewählt."""
    after_text = (data.get("after_text") or "") if data.get("after") == "text" else ""
    name = ""
    target = None
    if data.get("mode") == "date":
        if not data.get("at"):
            return None
        try:
            target = timezone.make_aware(datetime.datetime.strptime(data["at"], "%Y-%m-%dT%H:%M"))
        except ValueError:
            return None
    else:
        if not data.get("event"):
            return None
        occurrence = next_occurrence(site, data["event"])
        if occurrence is not None and not occurrence.is_cancelled:
            target = occurrence.starts_at
            name = occurrence.event.title
    if target is None or target <= timezone.now():
        if not after_text:
            return None
        return {"title": title, "target": "", "name": "", "text": "", "after_text": after_text}
    return {
        "title": title,
        "target": target.isoformat(),
        "name": name,
        "text": data.get("text") or "",
        "after_text": after_text,
    }


def _directions(site, title, data) -> dict | None:
    from events import maps
    from places.models import Place

    if not data.get("place"):
        return None
    place = (
        Place.objects.filter(pk=data["place"], organization=site.area, is_active=True)
        .exclude(parent__is_active=False)
        .select_related("parent")
        .first()
    )
    if place is None:
        return None
    # Raum: Anschrift, Anfahrt und Kartenpunkt vom Gebäude
    shown = place.effective()
    route = maps.links(shown["name"], shown["address"], shown["latitude"], shown["longitude"])
    return {
        "title": title or shown["name"],
        "name": shown["name"],
        "address": shown["address"],
        "directions": shown["directions"],
        "text": data.get("text") or "",
        "route_url": route.get("osm"),
    }


def _event_list(site, title, data, event_entry) -> dict | None:
    from events.models import EventCategory

    from .public_views import _events

    if not data.get("category"):
        return None
    category = EventCategory.objects.filter(pk=data["category"], organization=site.area).first()
    if category is None:
        return None
    now = timezone.now()
    found = sorted(
        (
            o
            for o in _events(site, None)
            if o.event.category_id == category.pk and (o.ends_at or o.starts_at) >= now
        ),
        key=lambda o: o.starts_at,
    )[: data.get("count", 4)]
    return {
        "title": title or category.name,
        "category": category.name,
        "events": [event_entry(site, o) for o in found],
    }


def _document(site, title, data) -> dict | None:
    from . import documents
    from .content_models import WebsiteDocument

    if not data.get("document"):
        return None
    doc = WebsiteDocument.objects.filter(pk=data["document"], website=site.site).first()
    if doc is None or documents.find(site, doc.key) is None:
        return None
    return {
        "title": title,
        "label": data.get("label") or doc.title,
        "url": site.url(f"files/{doc.key}/"),
        "file_type": "pdf" if doc.content_type == "application/pdf" else "image",
        "size": doc.size,
    }


def _chronicle(site, title, data) -> dict | None:
    from .content_models import WebsiteText

    if not site.chronicle_on:
        return None
    t = site.published_texts().filter(kind=WebsiteText.Kind.PAGE, slug="geschichte").first()
    if t is None:
        return None
    entries = [e for e in site.timeline(t) if e["kind"] != "chapter" and e["title"]]
    entries.sort(key=lambda e: (e.get("until") or e["year"], e["year"]), reverse=True)
    entries = entries[: data.get("count", 3)]
    if not entries:
        return None
    return {
        "title": title,
        "entries": [
            {"year": e["year"], "until": e.get("until"), "title": e["title"], "text": e["text"]}
            for e in entries
        ],
    }


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
