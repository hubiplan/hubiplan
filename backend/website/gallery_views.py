"""Galerie in der Verwaltung (Recht „Inhalte der Webseite bearbeiten“, Ralf 05.11.2026)."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import diff, record, snapshot
from core.api_base import ModelCleanMixin
from core.reorder import reorder_response

from . import gallery
from .content_models import ALBUM_ORDERS, DEFAULT_ALBUM_ORDER, IMAGE_ORDERS, GalleryAlbum
from .content_views import _ContentMixin, image_data


class AlbumSerializer(ModelCleanMixin, serializers.ModelSerializer):
    slug = serializers.CharField(max_length=60, required=False, allow_blank=True)

    class Meta:
        model = GalleryAlbum
        fields = [
            "parent",
            "title",
            "slug",
            "description",
            "date",
            "cover",
            "published",
            "show_captions",
            "image_order",
            "children_order",
        ]

    def extra_clean_attrs(self) -> dict:
        return {"website": self.context["website"]}

    def validate_parent(self, value):
        if value is not None and value.website_id != self.context["website"].pk:
            raise serializers.ValidationError(gettext("Unbekanntes Album."))
        return value

    def validate_cover(self, value):
        if value is not None and value.website_id != self.context["website"].pk:
            raise serializers.ValidationError(gettext("Unbekanntes Bild."))
        return value

    def validate(self, attrs):
        if not (attrs.get("slug") or (self.instance and self.instance.slug)):
            title = attrs.get("title") or (self.instance.title if self.instance else "")
            attrs["slug"] = gallery.suggest_slug(
                self.context["website"], title, exclude=self.instance.pk if self.instance else None
            )
        elif "slug" in attrs and not attrs["slug"]:
            attrs.pop("slug")
        slug = attrs.get("slug")
        if slug and (
            GalleryAlbum.objects.filter(website=self.context["website"], slug=slug)
            .exclude(pk=self.instance.pk if self.instance else None)
            .exists()
        ):
            raise serializers.ValidationError(
                {"slug": gettext("Diese Adresse hat schon ein anderes Album.")}
            )
        return super().validate(attrs)


def album_data(org_id: int, album: GalleryAlbum, *, full: bool = False) -> dict:
    data = {
        "id": album.pk,
        "parent": album.parent_id,
        "title": album.title,
        "slug": album.slug,
        "description": album.description,
        "date": album.date.isoformat() if album.date else None,
        "cover": album.cover_id,
        "published": album.published,
        "show_captions": album.show_captions,
        "image_order": album.image_order,
        "children_order": album.children_order,
        "position": album.position,
        "image_count": getattr(album, "n", None)
        if getattr(album, "n", None) is not None
        else album.items.count(),
        "updated_at": album.updated_at,
    }
    if full:
        data["images"] = [image_data(org_id, i) for i in gallery.album_images(album)]
    else:
        first = album.cover or next(iter(gallery.album_images(album)[:1]), None)
        data["cover_url"] = image_data(org_id, first)["small_url"] if first else None
    return data


class _AlbumMixin(_ContentMixin):
    def album(self) -> GalleryAlbum:
        return get_object_or_404(
            GalleryAlbum.objects.select_related("cover", "parent"),
            website=self.website(),
            pk=self.kwargs["pk"],
        )


class AlbumListView(_ContentMixin, APIView):
    """GET: alle Alben (mit Oberalbum) · POST: neues Album."""

    def get(self, request, org_id: int):
        website = self.website()
        return Response(self.listing(website))

    def listing(self, website) -> dict:
        albums = list(
            GalleryAlbum.objects.filter(website=website)
            .select_related("cover")
            .annotate(n=Count("items"))
        )
        return {
            "albums": [album_data(self.org.pk, a) for a in gallery.ordered_tree(website, albums)],
            "block_on": website.block_on("gallery"),
            "gallery_order": website.gallery_order or DEFAULT_ALBUM_ORDER,
            "image_orders": [{"value": k, "label": str(v)} for k, v in IMAGE_ORDERS.items()],
            "album_orders": [{"value": k, "label": str(v)} for k, v in ALBUM_ORDERS.items()],
        }

    @transaction.atomic
    def put(self, request, org_id: int):
        """Sortierung der Alben auf der Galerie-Seite."""
        website = self.website()
        order = request.data.get("gallery_order")
        if order not in ALBUM_ORDERS:
            raise serializers.ValidationError({"gallery_order": gettext("Unbekannte Sortierung.")})
        if website.gallery_order != order:
            record(
                self.org,
                request.user,
                "update",
                website,
                {"Alben sortieren nach": [website.gallery_order, order]},
            )
            website.gallery_order = order
            website.save(update_fields=["gallery_order"])
        return Response(self.listing(website))

    @transaction.atomic
    def post(self, request, org_id: int):
        website = self.website()
        ser = AlbumSerializer(data=request.data, context={"website": website})
        ser.is_valid(raise_exception=True)
        album = ser.save(organization=self.org, website=website, updated_by=request.user)
        record(self.org, request.user, "create", album, diff({}, snapshot(album)))
        return Response(album_data(self.org.pk, album, full=True), status=status.HTTP_201_CREATED)


class AlbumOrderView(_ContentMixin, APIView):
    """POST {ids, parent}: Reihenfolge der Alben einer Ebene (per Ziehen)."""

    def post(self, request, org_id: int):
        parent = request.data.get("parent")
        albums = GalleryAlbum.objects.filter(website=self.website(), parent_id=parent or None)
        return reorder_response(request, self.org, albums, "position")


class AlbumDetailView(_AlbumMixin, APIView):
    """GET: Album mit Bildern · PUT: Angaben (und mit ``images`` die Bilder in Reihenfolge)
    · DELETE: Album samt Unteralben löschen (die Bilder bleiben in der Bilderverwaltung)."""

    def get(self, request, org_id: int, pk: int):
        return Response(album_data(self.org.pk, self.album(), full=True))

    @transaction.atomic
    def put(self, request, org_id: int, pk: int):
        album = self.album()
        before = snapshot(album)
        ser = AlbumSerializer(
            album, data=request.data, partial=True, context={"website": album.website}
        )
        ser.is_valid(raise_exception=True)
        ser.save(updated_by=request.user)
        changes = diff(before, snapshot(album))
        changes.pop("updated_by", None)
        if "images" in request.data:
            count = album.items.count()
            gallery.set_images(album, request.data.get("images"))
            new = album.items.count()
            if new != count:
                changes["Bilder"] = [count, new]
        if changes:
            record(self.org, request.user, "update", album, changes)
        return Response(album_data(self.org.pk, album, full=True))

    @transaction.atomic
    def delete(self, request, org_id: int, pk: int):
        album = self.album()
        for child in album.children.all():
            record(self.org, request.user, "delete", child, {"Album": [str(child), None]})
        record(self.org, request.user, "delete", album, {"Album": [str(album), None]})
        album.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AlbumImagesView(_AlbumMixin, APIView):
    """POST {images: [ids]}: Bilder hinten an das Album anfügen (nach dem Hochladen)."""

    @transaction.atomic
    def post(self, request, org_id: int, pk: int):
        album = self.album()
        ids = request.data.get("images")
        count = album.items.count()
        gallery.add_images(album, ids if isinstance(ids, list) else [])
        new = album.items.count()
        if new != count:
            record(self.org, request.user, "update", album, {"Bilder": [count, new]})
        return Response(album_data(self.org.pk, album, full=True))
