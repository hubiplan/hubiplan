"""Chronik der Einheit über die KI-Schnittstelle (docs/mcp.md).

Die Chronik ist die Textseite „geschichte“ mit Einleitung und Zeitleiste (Modul „Chronik“,
``website.timeline``). Die Werkzeuge rufen dieselben Ansichten wie Verein › Chronik auf
(``ChronicleView`` und ``TextDetailView``): gleiche Rechte (Chronik pflegen oder Inhalte der
Webseite bearbeiten), gleiche Prüfung der Einträge, Änderungsprotokoll. Gespeichert wird nur
der Entwurf; veröffentlicht wird in HUBIplan.

Einträge haben keine feste Kennung. Sie werden über ihre Nummer in der Liste angesprochen,
die chronik_ansehen liefert; nach jeder Änderung steht die Liste wieder nach Jahren sortiert
(wie in der Oberfläche), daher liefern die Werkzeuge die neuen Nummern gleich mit.
"""

from __future__ import annotations

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from .club import ClubContext, _alt_hint, _dump, _schema, _str
from .oauth import SCOPE_DRAFT, SCOPE_READ
from .tools import Tool, ToolError

MAX_INTRO = 50_000
MAX_TITLE = 200
# Höchstens so viele Einträge auf einmal anlegen (Größe einer Anfrage)
MAX_BATCH = 100

KINDS = {"ereignis": "event", "kapitel": "chapter"}
POSITIONS = {"auto": "auto", "links": "left", "rechts": "right", "unten": "below"}
KIND_NAMES = {v: k for k, v in KINDS.items()}
POSITION_NAMES = {v: k for k, v in POSITIONS.items()}


def _views():
    from website import content_views

    return content_views


def _load(ctx: ClubContext, *, write: bool = False) -> dict:
    """Chronik wie unter Verein › Chronik; legt sie wie dort bei Bedarf an."""
    from access.modules import module_on

    if not module_on(ctx.grant.organization, "chronicle"):
        raise ToolError(_("Das Modul „Chronik“ ist für diese Einheit nicht eingeschaltet."))
    try:
        data = ctx.call(_views().ChronicleView, "GET", "chronicle/")
    except ToolError as exc:
        raise ToolError(_("Die Chronik darfst du nicht sehen.")) from exc
    if data.get("text") is None:
        raise ToolError(_("Noch keine Chronik angelegt."))
    if write and not data.get("can_edit"):
        raise ToolError(_("Die Chronik darfst du nur lesen."))
    return data


def _entry_out(nr: int, e: dict) -> dict:
    row = {
        "nr": nr,
        "art": KIND_NAMES.get(e.get("kind"), "ereignis"),
        "jahr": e.get("year"),
        "bis": e.get("until"),
        "ueberschrift": e.get("title", ""),
        "text": e.get("text", ""),
    }
    if row["art"] == "ereignis":
        from website.timeline import entry_images

        row["bilder"] = entry_images(e)
        row["bildposition"] = POSITION_NAMES.get(e.get("image_position") or "auto", "auto")
    return row


def _rows(timeline: list) -> list[dict]:
    return [_entry_out(nr, e) for nr, e in enumerate(timeline, start=1)]


def _summary(text: dict) -> dict:
    timeline = list(text.get("timeline") or [])
    data = {
        "titel": text.get("title"),
        "einleitung": text.get("body", ""),
        "neueste_zuerst": bool(text.get("timeline_newest_first")),
        "veroeffentlicht": text.get("is_published"),
        "entwurf_geaendert": text.get("has_changes"),
        "anzahl": len(timeline),
        "eintraege": _rows(timeline),
    }
    if text.get("revisions"):
        data["fruehere_fassungen"] = len(text["revisions"])
    return data


def _draft_hint() -> str:
    return _(
        "Gespeichert als Entwurf der Chronik. Öffentlich wird er erst, wenn jemand ihn in "
        "HUBIplan unter Chronik veröffentlicht; frühere Fassungen lassen sich dort wieder holen."
    )


def _year(value, name: str, *, empty: bool = False) -> int | None:
    if value is None and empty:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolError(_("„%(name)s“ muss eine Jahreszahl sein.") % {"name": name})
    return value


def _apply(entry: dict, args: dict, *, new: bool) -> dict:
    """Werte aus dem Werkzeug in einen Eintrag der Zeitleiste übernehmen."""
    result = dict(entry)
    if "art" in args or new:
        kind = args.get("art", "ereignis")
        if kind not in KINDS:
            raise ToolError(_("„art“ muss ereignis oder kapitel sein."))
        result["kind"] = KINDS[kind]
    if "jahr" in args or new:
        result["year"] = _year(args.get("jahr"), "jahr")
    if "bis" in args:
        result["until"] = _year(args["bis"], "bis", empty=True)
    elif new:
        result["until"] = None
    if "ueberschrift" in args or new:
        title = args.get("ueberschrift")
        if not isinstance(title, str) or not title.strip():
            raise ToolError(_("„%(name)s“ fehlt.") % {"name": "ueberschrift"})
        result["title"] = title.strip()
    if "text" in args:
        value = args["text"]
        if value is not None and not isinstance(value, str):
            raise ToolError(_("„%(name)s“ muss ein Text sein.") % {"name": "text"})
        result["text"] = value or ""
    elif new:
        result["text"] = ""
    if "bilder" in args:
        value = args["bilder"]
        if not isinstance(value, list) or not all(
            isinstance(v, int) and not isinstance(v, bool) for v in value
        ):
            raise ToolError(_("„bilder“ muss eine Liste von Bildnummern sein."))
        result["images"] = value
        result.pop("image", None)
    elif new:
        result["images"] = []
    if "bildposition" in args:
        if args["bildposition"] not in POSITIONS:
            raise ToolError(_("„bildposition“ muss auto, links, rechts oder unten sein."))
        result["image_position"] = POSITIONS[args["bildposition"]]
    elif new:
        result["image_position"] = "auto"
    if result.get("kind") == "chapter":
        if args.get("bilder"):
            raise ToolError(_("Kapitel haben keine Bilder."))
        result["images"], result["image_position"] = [], "auto"
    return result


def _save(ctx: ClubContext, text: dict, body: dict) -> dict:
    pk = text["id"]
    if "timeline" in body:
        from website.timeline import sorted_timeline

        # Wie die Oberfläche: nach Jahr, Kapitel vor den Ereignissen ihres Jahres
        body["timeline"] = sorted_timeline(body["timeline"])
    return ctx.call(_views().TextDetailView, "PUT", f"website/texts/{pk}/", body, pk=pk)


def _positions(timeline: list, wanted: list[dict]) -> list[int]:
    """Nummern (ab 1) der gewünschten Einträge in der neu sortierten Liste."""
    taken: set[int] = set()
    result = []
    for entry in wanted:
        for nr, e in enumerate(timeline, start=1):
            if nr in taken:
                continue
            if (e.get("kind"), e.get("year"), e.get("title")) == (
                entry.get("kind"),
                entry.get("year"),
                entry.get("title"),
            ):
                taken.add(nr)
                result.append(nr)
                break
    return result


def _nr(args: dict, timeline: list) -> int:
    nr = args.get("nr")
    if isinstance(nr, bool) or not isinstance(nr, int) or not 1 <= nr <= len(timeline):
        raise ToolError(
            _("Einen Eintrag mit dieser Nummer gibt es nicht (1 bis {n}).").format(n=len(timeline))
        )
    expected = args.get("ueberschrift_bisher")
    if expected is not None and str(expected).strip() != timeline[nr - 1].get("title"):
        raise ToolError(
            _(
                "Eintrag {nr} heißt inzwischen „{title}“. Bitte die Chronik mit chronik_ansehen "
                "neu laden."
            ).format(nr=nr, title=timeline[nr - 1].get("title"))
        )
    return nr


def _images_of(entries: list[dict]) -> list[int]:
    return [pk for e in entries for pk in e.get("images") or []]


def _changed(ctx: ClubContext, saved: dict, entries: list[dict], message: str) -> str:
    timeline = list(saved.get("timeline") or [])
    numbers = _positions(timeline, entries)
    rows = [_entry_out(nr, timeline[nr - 1]) for nr in numbers]
    return (
        message
        + " "
        + _draft_hint()
        + _alt_hint(ctx, _images_of(entries))
        + "\n\n"
        + _dump({"anzahl": len(timeline), "eintraege": rows})
    )


# --- Werkzeuge ---


def _read(args: dict, ctx: ClubContext) -> str:
    data = _load(ctx)
    hint = _(
        "Chronik im Entwurf: Einleitung und Zeitleiste, nach Jahren sortiert. „nr“ ist die "
        "Stelle in dieser Liste; sie ändert sich, wenn Einträge dazukommen oder wegfallen. "
        "Kapitel sind Zwischenüberschriften für alle Ereignisse ab ihrem Jahr. Bilder sind "
        "Nummern aus webseite_bilder. Ändern darf: {can}."
    ).format(can=_("ja") if data.get("can_edit") else _("nein"))
    return hint + "\n\n" + _dump(_summary(data["text"]))


def _change(args: dict, ctx: ClubContext) -> str:
    text = _load(ctx, write=True)["text"]
    body: dict = {}
    title = _str(args, "titel", MAX_TITLE)
    if title is not None:
        if not title.strip():
            raise ToolError(_("„titel“ darf nicht leer sein."))
        body["title"] = title.strip()
    intro = _str(args, "einleitung", MAX_INTRO)
    if intro is not None:
        body["body"] = intro
    if "neueste_zuerst" in args:
        if not isinstance(args["neueste_zuerst"], bool):
            raise ToolError(_("„%(name)s“ ist ja oder nein.") % {"name": "neueste_zuerst"})
        body["timeline_newest_first"] = args["neueste_zuerst"]
    if not body:
        raise ToolError(_("Bitte titel, einleitung oder neueste_zuerst angeben."))
    saved = _save(ctx, text, body)
    return (
        _("Chronik geändert ({keys}).").format(keys=", ".join(sorted(body)))
        + " "
        + _draft_hint()
        + "\n\n"
        + _dump({k: v for k, v in _summary(saved).items() if k != "eintraege"})
    )


def _create(args: dict, ctx: ClubContext) -> str:
    raw = args.get("eintraege")
    if not isinstance(raw, list) or not raw:
        raise ToolError(_("„eintraege“ muss eine Liste mit mindestens einem Eintrag sein."))
    if len(raw) > MAX_BATCH:
        raise ToolError(
            _("Höchstens {n} Einträge auf einmal; den Rest bitte in einem zweiten Aufruf.").format(
                n=MAX_BATCH
            )
        )
    entries = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ToolError(_("Eintrag {n} muss ein Objekt sein.").format(n=index))
        try:
            entries.append(_apply({}, item, new=True))
        except ToolError as exc:
            raise ToolError(_("Eintrag {n}: {error}").format(n=index, error=exc)) from exc
    text = _load(ctx, write=True)["text"]
    timeline = list(text.get("timeline") or []) + entries
    saved = _save(ctx, text, {"timeline": timeline})
    return _changed(
        ctx,
        saved,
        entries,
        _("{n} Einträge in die Chronik aufgenommen.").format(n=len(entries))
        if len(entries) != 1
        else _("Eintrag in die Chronik aufgenommen."),
    )


def _edit(args: dict, ctx: ClubContext) -> str:
    text = _load(ctx, write=True)["text"]
    timeline = list(text.get("timeline") or [])
    nr = _nr(args, timeline)
    fields = {k: v for k, v in args.items() if k not in ("nr", "ueberschrift_bisher", "sprache")}
    if not fields:
        raise ToolError(_("Bitte angeben, was sich am Eintrag ändern soll."))
    entry = _apply(timeline[nr - 1], fields, new=False)
    timeline[nr - 1] = entry
    saved = _save(ctx, text, {"timeline": timeline})
    return _changed(ctx, saved, [entry], _("Eintrag {nr} geändert.").format(nr=nr))


def _delete(args: dict, ctx: ClubContext) -> str:
    text = _load(ctx, write=True)["text"]
    timeline = list(text.get("timeline") or [])
    nr = _nr(args, timeline)
    removed = timeline.pop(nr - 1)
    saved = _save(ctx, text, {"timeline": timeline})
    return (
        _("Eintrag {nr} „{title}“ ({year}) aus dem Entwurf entfernt.").format(
            nr=nr, title=removed.get("title"), year=removed.get("year")
        )
        + " "
        + _draft_hint()
        + "\n\n"
        + _dump({"anzahl": len(saved.get("timeline") or [])})
    )


NAMES_HINT = gettext_lazy(
    "Die Chronik wird mit dem Veröffentlichen öffentlich: Lebende Personen nur nennen, wenn "
    "sie der Nennung in „Würden und Chronik“ nicht widersprochen haben; HUBIplan prüft Namen "
    "im Freitext nicht."
)


def _described(text) -> str:
    return f"{text} {NAMES_HINT}"


class _Lazy:
    """Beschreibung aus zwei übersetzbaren Teilen (erst bei Abruf in der Anfragesprache)."""

    def __init__(self, text):
        self.text = text

    def __str__(self) -> str:
        return _described(self.text)


ENTRY = {
    "art": {
        "type": "string",
        "enum": list(KINDS),
        "description": gettext_lazy(
            "ereignis (Standard) oder kapitel (Zwischenüberschrift ab diesem Jahr, ohne Bilder)."
        ),
    },
    "jahr": {"type": "integer", "minimum": 1000, "maximum": 2999},
    "bis": {
        "type": ["integer", "null"],
        "minimum": 1000,
        "maximum": 2999,
        "description": gettext_lazy("Endjahr eines Zeitraums, z. B. 1939 bis 1948; null: keins."),
    },
    "ueberschrift": {"type": "string", "maxLength": 120},
    "text": {
        "type": "string",
        "maxLength": 400,
        "description": gettext_lazy("Kurzer Text, höchstens 400 Zeichen."),
    },
    "bilder": {
        "type": "array",
        "items": {"type": "integer", "minimum": 1},
        "maxItems": 6,
        "description": gettext_lazy(
            "Bis zu 6 Bildnummern aus webseite_bilder, in dieser Reihenfolge; [] entfernt alle."
        ),
    },
    "bildposition": {
        "type": "string",
        "enum": list(POSITIONS),
        "description": gettext_lazy("auto (abwechselnd), links, rechts oder unten (groß)."),
    },
}
NR = {"type": "integer", "minimum": 1, "description": gettext_lazy("Nummer aus chronik_ansehen.")}
CHECK = {
    "type": "string",
    "description": gettext_lazy(
        "Überschrift des Eintrags laut chronik_ansehen; stimmt sie nicht mehr, ändert sich "
        "nichts (Schutz, falls jemand die Chronik inzwischen geändert hat)."
    ),
}

CHRONICLE_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="chronik_ansehen",
        title=gettext_lazy("Chronik ansehen"),
        description=gettext_lazy(
            "Chronik (Vereinsgeschichte) im Entwurf: Titel, Einleitung, Reihenfolge der "
            "Zeitleiste und alle Einträge mit Nummer, Jahr oder Zeitraum, Überschrift, Text und "
            "Bildern; dazu, ob der Entwurf veröffentlicht ist. Braucht das Modul „Chronik“."
        ),
        schema=_schema(),
        run=_read,
        scope=SCOPE_READ,
    ),
    Tool(
        name="chronik_aendern",
        title=gettext_lazy("Chronik ändern"),
        description=_Lazy(
            gettext_lazy(
                "Ändert Titel und Einleitung der Chronik (Markdown) und ob die Webseite die "
                "neuesten Einträge zuerst zeigt. Nur im Entwurf; nur Angegebenes ändert sich. "
                "Braucht das Recht, die Chronik zu pflegen."
            )
        ),
        schema=_schema(
            {
                "titel": {"type": "string", "maxLength": MAX_TITLE},
                "einleitung": {"type": "string", "maxLength": MAX_INTRO},
                "neueste_zuerst": {"type": "boolean"},
            }
        ),
        run=_change,
        writes=True,
        scope=SCOPE_DRAFT,
    ),
    Tool(
        name="chronik_eintraege_anlegen",
        title=gettext_lazy("Einträge in die Chronik aufnehmen"),
        description=_Lazy(
            gettext_lazy(
                "Nimmt einen oder mehrere Einträge in die Zeitleiste der Chronik auf (z. B. aus "
                "einer Festschrift), je mit Jahr, Überschrift und kurzem Text, optional "
                "Endjahr und Bildern; Kapitel als Zwischenüberschriften. Die Liste wird nach "
                "Jahren sortiert. Nur im Entwurf. Braucht das Recht, die Chronik zu pflegen."
            )
        ),
        schema=_schema(
            {
                "eintraege": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": MAX_BATCH,
                    "items": {
                        "type": "object",
                        "properties": ENTRY,
                        "required": ["jahr", "ueberschrift"],
                        "additionalProperties": False,
                    },
                }
            },
            ["eintraege"],
        ),
        run=_create,
        writes=True,
        scope=SCOPE_DRAFT,
    ),
    Tool(
        name="chronik_eintrag_aendern",
        title=gettext_lazy("Chronik-Eintrag ändern"),
        description=_Lazy(
            gettext_lazy(
                "Ändert einen Eintrag der Zeitleiste (Nummer aus chronik_ansehen): Art, Jahr, "
                "Endjahr, Überschrift, Text, Bilder oder Bildposition. Nur Angegebenes ändert "
                "sich; die Liste wird danach nach Jahren sortiert. Nur im Entwurf."
            )
        ),
        schema=_schema({"nr": NR, "ueberschrift_bisher": CHECK, **ENTRY}, ["nr"]),
        run=_edit,
        writes=True,
        scope=SCOPE_DRAFT,
    ),
    Tool(
        name="chronik_eintrag_loeschen",
        title=gettext_lazy("Chronik-Eintrag entfernen"),
        description=gettext_lazy(
            "Entfernt einen Eintrag aus der Zeitleiste der Chronik (Nummer aus chronik_ansehen). "
            "Nur im Entwurf: Die veröffentlichte Fassung bleibt, bis jemand neu veröffentlicht, "
            "und frühere Fassungen lassen sich in HUBIplan zurückholen. Vorher die Person fragen."
        ),
        schema=_schema({"nr": NR, "ueberschrift_bisher": CHECK}, ["nr", "ueberschrift_bisher"]),
        run=_delete,
        writes=True,
        scope=SCOPE_DRAFT,
    ),
)
