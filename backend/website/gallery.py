"""Galerie der Webseite (Ralf 05.11.2026): Alben mit Bildern aus der Bilderverwaltung.

Höchstens zwei Ebenen: Ein Album (z. B. „2024“) enthält Bilder und/oder Unteralben
(z. B. „Schützenfest“). Auf der Webseite erscheint ein Album, wenn es „auf der Webseite
zeigen“ hat, sein Oberalbum ebenfalls sichtbar ist und der Bereich „Galerie“ an ist.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Count, Prefetch
from django.utils.text import slugify
from django.utils.translation import gettext
from rest_framework.exceptions import ValidationError

from .content_models import (
    ALBUM_ORDERS,
    DEFAULT_ALBUM_ORDER,
    DEFAULT_IMAGE_ORDER,
    IMAGE_ORDERS,
    MAX_ALBUM_IMAGES,
    RESERVED_SLUGS,
    GalleryAlbum,
    GalleryItem,
    WebsiteImage,
)

# Umlaute wie in Adressen üblich (slugify ließe sie sonst weg)
_UMLAUTE = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "ae", "Ö": "oe", "Ü": "ue", "ß": "ss"}
)


def suggest_slug(website, title: str, exclude: int | None = None) -> str:
    """Freie Adresse aus dem Titel, z. B. „Schützenfest 2024“ → „schuetzenfest-2024“."""
    base = slugify(title.translate(_UMLAUTE))[:50].strip("-") or "album"
    if base in RESERVED_SLUGS:
        base = f"album-{base}"
    others = GalleryAlbum.objects.filter(website=website).exclude(pk=exclude)
    taken = set(others.values_list("slug", flat=True))
    slug, n = base, 2
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    return slug


# --- Sortierung (Ralf 05.11.) ---


def _text_key(value: str) -> str:
    return (value or "").translate(_UMLAUTE).casefold()


def _desc(order: str) -> bool:
    return order.endswith("_desc")


def sort_items(items: list[GalleryItem], order: str) -> list[GalleryItem]:
    """Bilder eines Albums nach der gewählten Sortierung; leere Werte stehen hinten,
    bei Gleichstand gilt die eigene Reihenfolge."""
    order = order if order in IMAGE_ORDERS else DEFAULT_IMAGE_ORDER
    items = sorted(items, key=lambda i: (i.position, i.pk))
    if order == "manual":
        return items
    base = order.removesuffix("_desc")

    def value(i: GalleryItem):
        img = i.image
        if base == "taken":
            return img.taken_at or img.uploaded_at
        if base == "uploaded":
            return img.uploaded_at
        if base == "name":
            return _text_key(img.file_name)
        return _text_key(img.caption)

    filled = [i for i in items if value(i)]
    empty = [i for i in items if not value(i)]
    return sorted(filled, key=value, reverse=_desc(order)) + empty


def sort_albums(albums: list[GalleryAlbum], order: str) -> list[GalleryAlbum]:
    order = order if order in ALBUM_ORDERS else DEFAULT_ALBUM_ORDER
    albums = sorted(albums, key=lambda a: (a.position, a.pk))
    if order == "manual":
        return albums
    if order.startswith("title"):
        return sorted(albums, key=lambda a: _text_key(a.title), reverse=_desc(order))
    dated = [a for a in albums if a.date]
    undated = [a for a in albums if not a.date]
    return sorted(dated, key=lambda a: a.date, reverse=_desc(order)) + undated


def ordered_items(album: GalleryAlbum) -> list[GalleryItem]:
    items = list(album.items.select_related("image", "image__department"))
    return sort_items(items, album.image_order)


def album_images(album: GalleryAlbum) -> list[WebsiteImage]:
    return [i.image for i in ordered_items(album)]


def ordered_tree(website, albums: list[GalleryAlbum]) -> list[GalleryAlbum]:
    """Alle Alben in Anzeigereihenfolge: Hauptalben, jeweils gefolgt von ihren Unteralben."""
    children: dict[int, list[GalleryAlbum]] = {}
    for a in albums:
        if a.parent_id:
            children.setdefault(a.parent_id, []).append(a)
    result = []
    for top in sort_albums([a for a in albums if not a.parent_id], website.gallery_order):
        result.append(top)
        result += sort_albums(children.get(top.pk, []), top.children_order)
    return result


@transaction.atomic
def set_images(album: GalleryAlbum, ids: list[int]) -> None:
    """Bilder des Albums in dieser Reihenfolge (fehlende fallen heraus, bleiben aber
    in der Bilderverwaltung)."""
    if not isinstance(ids, list) or not all(
        isinstance(i, int) and not isinstance(i, bool) for i in ids
    ):
        raise ValidationError({"images": gettext("Erwartet eine Liste von Bildnummern.")})
    ids = list(dict.fromkeys(ids))
    if len(ids) > MAX_ALBUM_IMAGES:
        raise ValidationError(
            {"images": gettext("Ein Album fasst höchstens {n} Bilder.").format(n=MAX_ALBUM_IMAGES)}
        )
    known = set(
        WebsiteImage.objects.filter(website=album.website, pk__in=ids).values_list("pk", flat=True)
    )
    if len(known) != len(ids):
        raise ValidationError({"images": gettext("Unbekanntes Bild.")})
    current = {i.image_id: i for i in album.items.all()}
    for pk, item in current.items():
        if pk not in known:
            item.delete()
    for position, pk in enumerate(ids, start=1):
        item = current.get(pk)
        if item is None:
            GalleryItem.objects.create(
                organization=album.organization, album=album, image_id=pk, position=position
            )
        elif item.position != position:
            item.position = position
            item.save(update_fields=["position"])


def add_images(album: GalleryAlbum, ids: list[int]) -> None:
    """Bilder hinten anfügen (schon enthaltene bleiben, wo sie sind)."""
    existing = list(album.items.values_list("image_id", flat=True))
    set_images(album, existing + [i for i in ids if i not in existing])


# --- öffentlich ---


def visible_albums(website):
    """Alle Alben, die auf der Webseite erscheinen (eigene und Oberalbum veröffentlicht)."""
    if not website.block_on("gallery"):
        return GalleryAlbum.objects.none()
    return GalleryAlbum.objects.filter(website=website, published=True).exclude(
        parent__isnull=False, parent__published=False
    )


def visible_image_ids(website) -> set[int]:
    albums = visible_albums(website)
    ids = set(GalleryItem.objects.filter(album__in=albums).values_list("image_id", flat=True))
    ids.update(pk for pk in albums.values_list("cover_id", flat=True) if pk)
    return ids


def has_albums(website) -> bool:
    return visible_albums(website).filter(parent__isnull=True).exists()


def _image(show, image: WebsiteImage | None, captions: bool = True) -> dict | None:
    """Bild wie in der übrigen öffentlichen Schnittstelle (``show`` = PublicSite.image)."""
    data = show(image)
    if data is not None and not captions:
        data["caption"] = ""
    return data


def _cover(show, album: GalleryAlbum, first: dict) -> dict | None:
    """Titelbild: das gewählte, sonst das erste Bild (auch aus einem Unteralbum)."""
    return _image(show, album.cover if album.cover_id else first.get(album.pk), captions=False)


def _summaries(show, albums: list[GalleryAlbum], visible) -> list[dict]:
    """Kurzangaben je Album: Titel, Jahr, Titelbild, Zahl der Bilder und Unteralben."""
    ids = [a.pk for a in albums]
    children = {}
    for c in visible.filter(parent_id__in=ids).annotate(n=Count("items")):
        children.setdefault(c.parent_id, []).append(c)
    first: dict[int, WebsiteImage] = {}
    pool = {a.pk: a for a in albums} | {c.pk: c for cs in children.values() for c in cs}
    grouped: dict[int, list[GalleryItem]] = {}
    for item in GalleryItem.objects.filter(album_id__in=list(pool)).select_related("image"):
        grouped.setdefault(item.album_id, []).append(item)
    for pk, items in grouped.items():
        first[pk] = sort_items(items, pool[pk].image_order)[0].image
    for a in albums:
        if a.pk not in first:
            for c in sort_albums(children.get(a.pk, []), a.children_order):
                if c.cover_id:
                    first[a.pk] = c.cover
                    break
                if c.pk in first:
                    first[a.pk] = first[c.pk]
                    break
    result = []
    for a in albums:
        own = getattr(a, "n", None)
        if own is None:
            own = a.items.count()
        result.append(
            {
                "slug": a.slug,
                "title": a.title,
                "year": a.date.year if a.date else None,
                "date": a.date.isoformat() if a.date else None,
                "cover": _cover(show, a, first),
                "images": own + sum(c.n for c in children.get(a.pk, [])),
                "albums": len(children.get(a.pk, [])),
            }
        )
    return result


def public_list(website, show) -> list[dict]:
    visible = visible_albums(website)
    top = list(
        visible.filter(parent__isnull=True).select_related("cover").annotate(n=Count("items"))
    )
    return _summaries(show, sort_albums(top, website.gallery_order), visible)


def public_album(website, slug: str, show) -> dict | None:
    visible = visible_albums(website)
    album = (
        visible.filter(slug=slug)
        .select_related("cover", "parent")
        .prefetch_related(Prefetch("items", queryset=GalleryItem.objects.select_related("image")))
        .first()
    )
    if album is None:
        return None
    subs = list(visible.filter(parent=album).select_related("cover").annotate(n=Count("items")))
    subs = sort_albums(subs, album.children_order)
    return {
        "slug": album.slug,
        "title": album.title,
        "description": album.description,
        "year": album.date.year if album.date else None,
        "date": album.date.isoformat() if album.date else None,
        "parent": {"slug": album.parent.slug, "title": album.parent.title}
        if album.parent_id
        else None,
        "albums": _summaries(show, subs, visible),
        "images": [
            _image(show, i.image, album.show_captions)
            for i in sort_items(list(album.items.all()), album.image_order)
        ],
    }
