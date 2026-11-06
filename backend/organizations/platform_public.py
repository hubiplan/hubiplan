"""Erscheinungsbild der Instanz für Seiten ohne Einheit (White Label, W1).

Die Anmeldeseite und alle Seiten, auf denen noch keine Einheit feststeht, zeigen
Name, Farben und Logo der Plattform-Einheit statt des HUBIplan-Standards
(konzepte/white-label.md). Ohne Anmeldung lesbar; enthält nur, was ohnehin auf
der Anmeldeseite steht.
"""

from __future__ import annotations

from django.http import Http404, HttpResponse, JsonResponse
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import brand_icon, theme
from .models import Organization, PlatformSettings

PRODUCT_NAME = "HUBIplan"


def instance_name() -> str:
    """Name der Instanz für Mails und Texte (Vorgabe „HUBIplan“, White Label)."""
    name = (
        Organization.objects.filter(type=Organization.Type.PLATFORM)
        .values_list("name", flat=True)
        .first()
    )
    return (name or "").strip() or PRODUCT_NAME


class PlatformThemeSerializer(serializers.Serializer):
    primary = serializers.CharField()
    on_primary = serializers.CharField()
    accent = serializers.CharField()
    on_accent = serializers.CharField()


class PublicPlatformSerializer(serializers.Serializer):
    name = serializers.CharField()
    short_name = serializers.CharField(allow_blank=True)
    logo_url = serializers.CharField(allow_null=True)
    theme = PlatformThemeSerializer(allow_null=True)
    # True: eigenes Symbol unter /api/public/platform/icon-<Größe>.png und eigenes Manifest
    icon = serializers.BooleanField()


def platform_data() -> dict:
    """Name, Kurzname, Logo und eigene Farben der Plattform (theme None: Standardfarben)."""
    # Kein get_or_create: Ein Lesezugriff ohne Anmeldung legt nichts an
    platform = Organization.objects.filter(type=Organization.Type.PLATFORM).first()
    settings_row = PlatformSettings.objects.filter(pk=1).first()
    icon = bool(settings_row and settings_row.brand_icon)
    if platform is None:
        return {
            "name": PRODUCT_NAME,
            "short_name": "",
            "logo_url": None,
            "theme": None,
            "icon": icon,
        }
    own_colors = bool(platform.primary_color or platform.accent_color)
    effective = theme.effective_theme([platform]) if own_colors else None
    return {
        "name": platform.name or PRODUCT_NAME,
        "short_name": platform.short_name or "",
        "logo_url": platform.logo.url if platform.logo else None,
        "theme": (
            {k: effective[k] for k in ("primary", "on_primary", "accent", "on_accent")}
            if effective
            else None
        ),
        "icon": icon,
    }


class PublicPlatformView(APIView):
    """Erscheinungsbild der Instanz für die Anmeldeseite (ohne Anmeldung)."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(responses=PublicPlatformSerializer)
    def get(self, request):
        response = Response(platform_data())
        # Kurz zwischenspeichern: Änderungen sind nach spätestens fünf Minuten überall zu sehen
        response["Cache-Control"] = "public, max-age=300"
        return response


# --- Symbol und Manifest (White Label W2) ---

ICON_URL = "/api/public/platform/icon-{name}.png"
DEFAULT_ICONS = [
    {"src": "/favicon.svg", "sizes": "any", "type": "image/svg+xml"},
    {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
    {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
]
# Wie manifest.webmanifest im Frontend (Fläche aus dem Gestaltungshandbuch)
BACKGROUND_COLOR = "#f3f7f5"


def _icon_file() -> tuple[str, bytes] | None:
    row = PlatformSettings.objects.filter(pk=1).first()
    if not row or not row.brand_icon:
        return None
    try:
        with row.brand_icon.open("rb") as fh:
            return row.brand_icon.name, fh.read()
    except OSError:
        return None


class PublicPlatformIconView(APIView):
    """Symbol der Instanz in einer festen Größe (ohne Anmeldung)."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(responses={(200, "image/png"): bytes})
    def get(self, request, name: str):
        maskable = name == "maskable"
        size = 512 if maskable else int(name) if name.isdigit() else 0
        if size not in brand_icon.SIZES:
            raise Http404
        found = _icon_file()
        if found is None:
            raise Http404
        response = HttpResponse(
            brand_icon.render(found[0], found[1], size, maskable=maskable),
            content_type="image/png",
        )
        response["Cache-Control"] = "public, max-age=3600"
        return response


def manifest_data() -> dict:
    data = platform_data()
    colors = data["theme"] or {"primary": theme.DEFAULT_PRIMARY}
    if data["icon"]:
        icons = [
            {"src": ICON_URL.format(name=192), "sizes": "192x192", "type": "image/png"},
            {"src": ICON_URL.format(name=512), "sizes": "512x512", "type": "image/png"},
            {
                "src": ICON_URL.format(name="maskable"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
        ]
    else:
        icons = DEFAULT_ICONS
    name = data["name"]
    return {
        "name": name,
        # Kurzname für den Startbildschirm; ohne eigenen höchstens 12 Zeichen vom Namen
        "short_name": data["short_name"] or name[:12],
        "lang": "de",
        "start_url": "/",
        "display": "standalone",
        "background_color": BACKGROUND_COLOR,
        "theme_color": colors["primary"],
        "icons": icons,
    }


class PublicManifestView(APIView):
    """Web-App-Manifest mit Name, Farbe und Symbol der Instanz (ohne Anmeldung)."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(responses={(200, "application/manifest+json"): dict})
    def get(self, request):
        response = JsonResponse(manifest_data(), content_type="application/manifest+json")
        response["Cache-Control"] = "public, max-age=300"
        return response
