"""Bilder für die Webseite von außerhalb der Bilderverwaltung (KI-Schnittstelle, docs/mcp.md).

- **Hochladelink (W2):** Ein KI-Assistent legt für die Person hinter der Verbindung einen
  kurz gültigen Link an. Sie öffnet ihn auf Handy oder PC und wählt Fotos; die Dateien
  gehen nie über den Anbieter des Assistenten.
- **Bild per Adresse (W3):** HUBIplan holt ein Bild von einem Server, den die Einheit unter
  Webseite › Domain freigegeben hat (``Website.image_hosts``), über ``core.safehttp``
  (keine internen Adressen) und prüft es wie jeden Upload.

Beides legt nur Bilder in die Bilderverwaltung; öffentlich wird ein Bild erst, wenn es in
einem veröffentlichten Text oder Abschnitt steht.
"""

from __future__ import annotations

import urllib.parse

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.db.models import F
from django.http import Http404
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from access.modules import module_on
from audit.log import record
from core import safehttp
from core.ratelimit import client_ip, too_many
from core.tenancy import rls_bypass, tenant_context
from organizations.addresses import base_url
from organizations.imprint import ensure as ensure_imprint
from organizations.theme import effective_theme

from . import content
from .content_views import _ContentMixin, image_data
from .models import ImageUploadLink, hash_token

RATE_GET = (60, 600)  # Aufrufe je 10 Minuten und IP
RATE_POST = (40, 600)  # Bilder je 10 Minuten und IP
FETCH_TIMEOUT = 15
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")
CAPTION_MAX = 300


def _link_data(link: ImageUploadLink, url: str | None = None) -> dict:
    data = {
        "id": link.pk,
        "expires_at": link.expires_at,
        "max_files": link.max_files,
        "uploaded": link.uploaded,
        "open": link.is_open,
    }
    if url:
        data["url"] = url
    return data


class ImageUploadLinkView(_ContentMixin, APIView):
    """POST: Link zum Hochladen von Bildern anlegen (Adresse nur in dieser Antwort)."""

    parser_classes = [JSONParser]

    @transaction.atomic
    def post(self, request, org_id: int):
        website = self.website()
        via = request.data.get("via") if isinstance(request.data, dict) else ""
        link, token = ImageUploadLink.create(
            website, request.user, via if isinstance(via, str) else ""
        )
        record(
            self.org,
            request.user,
            "create",
            website,
            {
                "Hochladelink für Bilder": [
                    None,
                    f"gültig bis {timezone.localtime(link.expires_at):%d.%m.%Y %H:%M}"
                    + (f" ({link.via})" if link.via else ""),
                ]
            },
        )
        url = f"{base_url(self.org)}/bilder-hochladen/{token}"
        return Response(_link_data(link, url), status=status.HTTP_201_CREATED)


def _open_link(token: str) -> ImageUploadLink:
    with rls_bypass():
        link = (
            ImageUploadLink.objects.select_related("organization", "website", "created_by")
            .filter(token_hash=hash_token(token))
            .first()
        )
    if (
        link is None
        or not link.is_open
        or not link.organization.is_active
        or not link.created_by.is_active
        or not module_on(link.organization, "website")
    ):
        raise Http404
    return link


class PublicImageUploadView(APIView):
    """Seite des Hochladelinks (ohne Anmeldung): GET Angaben, POST ein Bild."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request, token: str):
        if too_many(f"web-upload:get:{client_ip(request)}", *RATE_GET):
            return Response({"detail": gettext("Zu viele Aufrufe. Bitte später erneut.")}, 429)
        link = _open_link(token)
        org = link.organization
        theme = effective_theme(org.ancestors())
        return Response(
            {
                "organization": org.name,
                "imprint_key": ensure_imprint(org).public_key,
                "logo_url": theme["logo_url"],
                "theme": {k: theme[k] for k in ("primary", "on_primary", "accent", "on_accent")},
                "expires_at": link.expires_at,
                "remaining": link.max_files - link.uploaded,
            }
        )

    def post(self, request, token: str):
        if too_many(f"web-upload:post:{client_ip(request)}", *RATE_POST):
            return Response({"detail": gettext("Zu viele Versuche. Bitte später erneut.")}, 429)
        link = _open_link(token)
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": gettext("Bitte ein Bild auswählen.")})
        org = link.organization
        with tenant_context(org.pk), transaction.atomic():
            # Platz belegen, bevor gespeichert wird; scheitert das Bild, zählt es nicht
            claimed = ImageUploadLink.objects.filter(
                pk=link.pk,
                revoked_at__isnull=True,
                expires_at__gt=timezone.now(),
                uploaded__lt=F("max_files"),
            ).update(uploaded=F("uploaded") + 1)
            if not claimed:
                raise Http404
            image = content.store_image(link.website, upload, "", "", link.created_by)
            record(
                org,
                link.created_by,
                "create",
                image,
                {"Bild": [None, f"{image} (über Hochladelink)"]},
            )
        link.refresh_from_db(fields=["uploaded"])
        return Response(
            {"id": image.pk, "remaining": link.max_files - link.uploaded},
            status=status.HTTP_201_CREATED,
        )


class ImageFetchSerializer(serializers.Serializer):
    url = serializers.CharField(max_length=2000)
    source = serializers.CharField(max_length=200)
    caption = serializers.CharField(max_length=CAPTION_MAX, required=False, allow_blank=True)
    alt_text = serializers.CharField(max_length=300, required=False, allow_blank=True)


def fetch(url: str, allowed: list[str]) -> SimpleUploadedFile:
    """Bild von einem freigegebenen Server holen (ValidationError mit lesbarem Text)."""
    parts = urllib.parse.urlsplit(url.strip())
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme != "https" or not host:
        raise ValidationError({"url": gettext("Bitte eine vollständige https-Adresse angeben.")})
    if host not in allowed:
        raise ValidationError(
            {
                "url": gettext(
                    "Von {host} dürfen keine Bilder geholt werden. Erlaubte Server stehen unter "
                    "Webseite › Domain › Bilder für KI-Assistenten."
                ).format(host=host)
            }
        )
    try:
        resp = safehttp.request(
            "GET",
            url.strip(),
            headers={"Accept": ", ".join(IMAGE_TYPES), "User-Agent": "HUBIplan"},
            timeout=FETCH_TIMEOUT,
            max_body=content.MAX_BYTES,
        )
    except safehttp.SafeHTTPError as exc:
        raise ValidationError({"url": gettext("Bild nicht erreichbar: {x}").format(x=exc)}) from exc
    if resp.status != 200:
        raise ValidationError(
            {"url": gettext("Der Server antwortet mit {status}.").format(status=resp.status)}
        )
    if len(resp.body) > content.MAX_BYTES:
        raise ValidationError({"url": gettext("Das Bild darf höchstens 15 MB groß sein.")})
    ctype = ""
    for key, value in resp.headers.items():
        if key.lower() == "content-type":
            ctype = value.split(";", 1)[0].strip().lower()
    if ctype not in IMAGE_TYPES:
        raise ValidationError(
            {"url": gettext("Unter dieser Adresse liegt kein JPG-, PNG- oder WebP-Bild.")}
        )
    name = urllib.parse.unquote(parts.path.rsplit("/", 1)[-1])[:100] or "bild"
    return SimpleUploadedFile(name, resp.body, content_type=ctype)


class ImageFetchView(_ContentMixin, APIView):
    """POST: Bild von einem freigegebenen Server in die Bilderverwaltung holen (W3)."""

    parser_classes = [JSONParser]

    def post(self, request, org_id: int):
        website = self.website()
        ser = ImageFetchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        values = ser.validated_data
        upload = fetch(values["url"], list(website.image_hosts or []))
        source = " ".join(values["source"].split())
        caption = " ".join((values.get("caption") or "").split())
        note = gettext("Quelle: {source}").format(source=source)
        caption = f"{caption} ({note})" if caption else note
        if len(caption) > CAPTION_MAX:
            raise ValidationError(
                {"caption": gettext("Bildunterschrift und Quelle sind zusammen zu lang.")}
            )
        with transaction.atomic():
            image = content.store_image(
                website, upload, caption, values.get("alt_text") or "", request.user
            )
            record(
                self.org,
                request.user,
                "create",
                image,
                {"Bild": [None, f"{image} (von {urllib.parse.urlsplit(values['url']).hostname})"]},
            )
        return Response(image_data(self.org.pk, image, used=False), status=status.HTTP_201_CREATED)
