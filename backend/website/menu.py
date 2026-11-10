"""Menü der Webseite als Baum (Ralf 2026-10-31): Reihenfolge per Ziehen, ein Punkt
auf einen anderen gezogen wird sein Unterpunkt, herausgezogen wieder Hauptpunkt.

Gespeichert wird nur die Anordnung (``Website.menu``): ``[{"key": …, "children":
[{"key": …}]}]``, höchstens zwei Ebenen. Ein- und ausgeschaltet werden die Bereiche
weiter über ``Website.blocks``. Punkte, die es (noch) nicht gibt, fallen weg; neue
Punkte kommen an ihren Standardplatz.

Schlüssel: die Bausteine aus ``BLOCKS`` (ohne „social“), ``page:<id>`` für eigene
Textseiten, ``dignity:<id>`` und ``honorary`` für die Unterpunkte von „Würdenträger“
(einzeln ausschaltbar über ``blocks`` mit demselben Schlüssel) und ``group:history``
für die Überschrift „Geschichte“, ``members`` mit ``membertype:<id>`` je Mitgliedsart
und ``memorial`` (Ralf 05.11.) sowie ``heading:<n>`` für frei benannte Überschriften
(Name in ``Website.block_names``) und ``link:<n>`` für Links nach außen (Name in
``block_names``, Adresse in ``Website.menu_links``, Ralf 10.11.). Ein Hauptpunkt kann als
Knopf hervorgehoben sein (``Website.menu_button``). Überschriften (``heading``)
haben keine eigene Seite; ohne Unterpunkte entfallen sie, mit nur einem steht dieser
direkt im Menü.
"""

from __future__ import annotations

from .models import BLOCK_HINTS, BLOCKS, Website, blocks_without_module, is_renamable

# Bausteine, die kein Menüpunkt sind
NOT_IN_MENU = {"social", "search"}
# Überschriften ohne eigene Seite: Schlüssel → (Bezeichnung, Standard-Unterpunkte)
HEADINGS = {"group:history": ("Geschichte", ("history", "offices"))}
# Textseite „Geschichte“ ist der Baustein „history“, kein eigener Menüpunkt
HISTORY_SLUG = "geschichte"
# Textseite „In Gedenken“ ist die Einleitung des Bausteins „memorial“ (Ralf 05.11.)
MEMORIAL_SLUG = "in-gedenken"


def _block_keys() -> list[str]:
    return [k for k in BLOCKS if k not in NOT_IN_MENU]


def items(
    website: Website,
    *,
    public_site=None,
    names: dict | None = None,
    links: dict | None = None,
) -> dict[str, dict]:
    """Alle möglichen Menüpunkte in Standardreihenfolge.

    Je Punkt: ``label`` (eigener Name oder Standard), ``default_label``,
    ``renamable``, ``hint``, ``toggle`` (Baustein-Schlüssel für ein/aus oder
    None), ``heading`` (Überschrift ohne eigene Seite), ``parent`` (Standard-
    Oberpunkt oder None). Mit ``public_site`` (SiteView) kommen öffentliche Angaben
    dazu (``visible``, ``slug``, ``id``). ``names``: eigene Namen, die noch nicht
    gespeichert sind (Prüfung einer Änderung mit neuen Überschriften), ``links`` ebenso
    für die Adressen neuer Links. Links tragen zusätzlich ``url``."""

    from .content_models import WebsiteText
    from .public import SiteView

    org = website.organization
    site = public_site or SiteView(website)
    result: dict[str, dict] = {}
    heading_of = {child: key for key, (_l, children) in HEADINGS.items() for child in children}
    off = blocks_without_module(org)
    if names is not None or links is not None:
        website = Website(
            pk=website.pk,
            organization=org,
            block_names=website.block_names if names is None else names,
            menu_links=website.menu_links if links is None else links,
            blocks=website.blocks,
        )

    def add(key, label, *, hint="", toggle=None, heading=False, parent=None, **extra):
        renamable = is_renamable(key)
        result[key] = {
            "label": (website.block_name(key) if renamable else "") or label,
            "default_label": label,
            "renamable": renamable,
            "hint": hint,
            "toggle": toggle,
            "heading": heading,
            "parent": parent,
            **extra,
        }

    pages = list(
        WebsiteText.objects.filter(website=website, kind=WebsiteText.Kind.PAGE)
        .exclude(slug__in=(HISTORY_SLUG, MEMORIAL_SLUG))
        .order_by("menu_position", "title", "pk")
    )
    for key in _block_keys():
        if key in heading_of and heading_of[key] not in result:
            label, _children = HEADINGS[heading_of[key]]
            add(heading_of[key], label, hint="Überschrift ohne eigene Seite", heading=True)
        if key == "statutes":
            # Eigene Textseiten stehen vor „Dokumente“
            for p in pages:
                state = []
                if p.published_at is None:
                    state.append("noch nicht veröffentlicht")
                if not p.show_in_menu:
                    state.append("unter Webseite › Texte aus dem Menü genommen")
                add(
                    f"page:{p.pk}",
                    p.title or p.published_title or p.slug,
                    hint="eigene Textseite" + (f" · {', '.join(state)}" if state else ""),
                    slug=p.slug,
                    visible=p.published_at is not None and p.show_in_menu,
                    public_label=p.published_title or p.slug,
                )
        # Bausteine abgeschalteter Module fehlen; „Würdenträger“ bleibt für die Ehrungen
        if key in off and key != "honors":
            continue
        label = BLOCKS[key]
        if key == "units":
            label = org.department_label_plural or label
        if key == "honors":
            honors_on = "honors" not in off
            honorary = [] if "honorary" in off else site.honorary()
            if not honors_on and not honorary:
                continue
            add(
                "honors",
                "Würdenträger",
                hint="Überschrift mit den Würden und Ehrungen",
                toggle="honors" if honors_on else None,
                heading=True,
            )
            for qs, _view, _owner, origins in site.dignity_sources() if honors_on else ():
                for d in site._with_reigns(qs, origins):
                    add(
                        f"dignity:{d.pk}",
                        d.plural if d.reign_count > 1 else d.name,
                        hint="Würde",
                        toggle=f"dignity:{d.pk}",
                        parent="honors",
                        id=site.token("dignity", d.pk),
                        visible=website.block_on("honors") and website.block_on(f"dignity:{d.pk}"),
                    )
            if honorary:
                add(
                    "honorary",
                    honorary[0]["heading"] if len(honorary) == 1 else "Ehrungen",
                    hint="Ehrungen und ihre Träger",
                    toggle="honorary",
                    parent="honors",
                    visible=website.block_on("honorary"),
                )
            continue
        if key == "members":
            # Überschrift mit einer Liste je Mitgliedsart (Ralf 05.11.); jede einzeln an
            add("members", label, hint=BLOCK_HINTS["members"], toggle="members", heading=True)
            for mt, slug in site.member_type_slugs().items():
                add(
                    f"membertype:{mt.pk}",
                    mt.name,
                    hint="Mitgliederliste dieser Mitgliedsart",
                    toggle=f"membertype:{mt.pk}",
                    parent="members",
                    id=slug,
                    visible=website.block_on("members")
                    and website.block_on(f"membertype:{mt.pk}")
                    and bool(site.member_list(mt)),
                )
            continue
        if key == "memorial":
            add(key, label, hint=BLOCK_HINTS[key], toggle=key, parent="members")
            continue
        add(key, label, hint=BLOCK_HINTS.get(key, ""), toggle=key, parent=heading_of.get(key))
    # Freie Überschriften (Ralf 05.11.): ohne festen Platz, neue stehen am Ende
    for key, name in website.headings().items():
        add(key, name, hint="eigene Überschrift ohne eigene Seite", heading=True)
    # Links nach außen (Ralf 10.11.): neue stehen am Ende
    for key, (name, url) in website.links().items():
        add(key, name, hint=f"Link nach außen · {url}", url=url)
    return result


def _clean(value) -> list[dict]:
    """Gespeicherte Anordnung → Liste von {key, children} (nur gültige Form)."""
    result = []
    for node in value if isinstance(value, list) else []:
        if not isinstance(node, dict) or not isinstance(node.get("key"), str):
            continue
        children = [
            {"key": c["key"]}
            for c in node.get("children") or []
            if isinstance(c, dict) and isinstance(c.get("key"), str)
        ]
        result.append({"key": node["key"], "children": children})
    return result


def normalize(value, known: dict[str, dict]) -> list[dict]:
    """Anordnung auf die bekannten Punkte bringen: Unbekanntes und Doppeltes fällt
    weg, Überschriften und Punkte mit Unterpunkten stehen oben, Fehlendes kommt an
    seinen Standardplatz (unter den Standard-Oberpunkt oder hinter den letzten
    Hauptpunkt, der in der Standardreihenfolge davor steht)."""
    order = {key: i for i, key in enumerate(known)}
    seen: set[str] = set()
    tree: list[dict] = []
    for node in _clean(value):
        key = node["key"]
        if key not in known or key in seen:
            continue
        seen.add(key)
        children = []
        for c in node["children"]:
            ck = c["key"]
            # Überschriften stehen immer oben (sie kommen unten an ihren Standardplatz)
            if ck in known and ck not in seen and not known[ck]["heading"]:
                seen.add(ck)
                children.append({"key": ck, "children": []})
        tree.append({"key": key, "children": children})
    for key, item in known.items():
        if key in seen:
            continue
        seen.add(key)
        new = {"key": key, "children": []}
        parent = item.get("parent")
        holder = next((n for n in tree if n["key"] == parent), None) if parent else None
        if holder is not None:
            siblings = holder["children"]
            at = next(
                (i for i, c in enumerate(siblings) if order.get(c["key"], 0) > order[key]),
                len(siblings),
            )
            siblings.insert(at, new)
            continue
        # hinter den letzten Hauptpunkt, der in der Standardreihenfolge davor steht
        before = [i for i, n in enumerate(tree) if order.get(n["key"], 0) < order[key]]
        tree.insert(before[-1] + 1 if before else 0, new)
    return tree


def validate(value, known: dict[str, dict]) -> list[dict]:
    """Prüft eine neue Anordnung aus der Verwaltung (wirft ValueError)."""
    if not isinstance(value, list):
        raise ValueError("Bitte das Menü als Liste angeben.")
    for node in _clean(value):
        if node["key"] not in known:
            continue
        if node["children"] and any(
            c["key"] in known and known[c["key"]]["heading"] for c in node["children"]
        ):
            raise ValueError("Eine Überschrift kann kein Unterpunkt sein.")
    for node in value:
        for c in (node.get("children") or []) if isinstance(node, dict) else []:
            if isinstance(c, dict) and c.get("children"):
                raise ValueError("Das Menü hat höchstens zwei Ebenen.")
    return normalize(value, known)


def public_nav(site) -> list[dict]:
    """Menü für die Webseite: nur sichtbare Punkte, je Punkt ``key``, ``label``,
    bei Textseiten ``slug``, bei Würden ``id``, bei Überschriften ``heading`` und
    bei Unterpunkten ``children``."""
    website = site.site
    known = items(website, public_site=site)

    def visible(key: str) -> bool:
        item = known[key]
        if "visible" in item:
            return bool(item["visible"])
        if item["heading"]:
            return True
        return _available(site, key)

    def entry(key: str) -> dict:
        item = known[key]
        out = {"key": key.split(":", 1)[0], "label": item.get("public_label") or item["label"]}
        if key.startswith("page:"):
            out["slug"] = item["slug"]
        if key.startswith(("dignity:", "membertype:")):
            out["id"] = item["id"]
        if key.startswith("link:"):
            out["url"] = item["url"]
        if key == "honors" and not item["heading"]:
            out["label"] = site.honors_label()
        if item["heading"]:
            out["heading"] = True
        return out

    result = []
    for node in normalize(website.menu, known):
        children = [entry(c["key"]) for c in node["children"] if visible(c["key"])]
        if not visible(node["key"]) and not known[node["key"]]["heading"]:
            # Ausgeschalteter Oberpunkt: seine Unterpunkte rücken nach oben
            result += children
            continue
        top = entry(node["key"])
        if top.get("heading"):
            if not children:
                continue
            if len(children) == 1:
                result.append(children[0])
                continue
        if children:
            top["children"] = children
        # Knopf nur für einen einfachen Hauptpunkt (keine Überschrift, kein Aufklappmenü)
        if node["key"] == website.menu_button and not top.get("heading") and not children:
            top["button"] = True
        result.append(top)
    return result


def _available(site, key: str) -> bool:
    """Ist der Bereich eingeschaltet und hat er Inhalt (wie bisher das Menü der Webseite)?"""
    website = site.site
    if key not in BLOCKS or not website.block_on(key):
        return False
    if key == "posts":
        return any(site.posts_available().values())
    if key == "units":
        return bool(site.units)
    if key == "gallery":
        from . import gallery

        return gallery.has_albums(website)
    if key == "statutes":
        from . import documents
        from .public_views import DOCUMENT_KINDS, _statute_publication

        # Satzung, Beitragsordnung, Gründungsurkunde oder eigene Dokumente öffentlich
        return any(_statute_publication(site, kind) is not None for kind in DOCUMENT_KINDS) or bool(
            documents.public_list(site, "documents")
        )
    if key == "history":
        return site.page(HISTORY_SLUG) is not None
    if key == "offices":
        return site.has_chairs()
    if key == "memorial":
        return bool(site.memorial())
    if key == "repertoire":
        return bool(site.repertoire())
    if key == "press":
        from . import documents

        return bool(documents.public_list(site, "press"))
    if key == "results":
        from . import results

        return results.available(site)
    if key == "bookings":
        from bookings import public as bookings

        return bookings.available(site)
    return True
