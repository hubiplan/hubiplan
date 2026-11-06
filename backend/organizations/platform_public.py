"""Erscheinungsbild der Instanz für Seiten ohne Einheit (White Label, W1).

Die Anmeldeseite und alle Seiten, auf denen noch keine Einheit feststeht, zeigen
Name, Farben und Logo der Plattform-Einheit statt des HUBIplan-Standards
(konzepte/white-label.md). Ohne Anmeldung lesbar; enthält nur, was ohnehin auf
der Anmeldeseite steht.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import theme
from .models import Organization

PRODUCT_NAME = "HUBIplan"


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


def platform_data() -> dict:
    """Name, Kurzname, Logo und eigene Farben der Plattform (theme None: Standardfarben)."""
    # Kein get_or_create: Ein Lesezugriff ohne Anmeldung legt nichts an
    platform = Organization.objects.filter(type=Organization.Type.PLATFORM).first()
    if platform is None:
        return {"name": PRODUCT_NAME, "short_name": "", "logo_url": None, "theme": None}
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
