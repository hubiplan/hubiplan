"""Adressen der KI-Schnittstelle (docs/mcp.md)."""

from django.urls import path, re_path
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from . import oauth_views
from .views import McpClubView, McpView


class _McpNoSlash(McpView):
    """Wie /api/mcp/, ohne Schrägstrich; eigene operationId im Schema."""

    @extend_schema(
        operation_id="mcp_create_ohne_schraegstrich",
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT, 202: None},
        description="Wie POST /api/mcp/ (Adresse ohne Schrägstrich, ohne Weiterleitung).",
    )
    def post(self, request):
        return super().post(request)


class _McpClubNoSlash(McpClubView):
    """Wie /api/mcp/verein/, ohne Schrägstrich; eigene operationId im Schema."""

    @extend_schema(
        operation_id="mcp_verein_create_ohne_schraegstrich",
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT, 202: None, 401: OpenApiTypes.OBJECT},
        description="Wie POST /api/mcp/verein/ (Adresse ohne Schrägstrich, ohne Weiterleitung).",
    )
    def post(self, request):
        return super().post(request)


api_patterns = [
    # Stufe 0: nur Hilfe, ohne Anmeldung
    path("mcp/", McpView.as_view(), name="mcp"),
    # Stufe 1a: mit Anmeldung, Webseite der verbundenen Einheit (W1)
    path("mcp/verein/", McpClubView.as_view(), name="mcp-club"),
    # Ohne Schrägstrich ebenso, ohne Weiterleitung: claude.ai prüft die Adresse so und
    # bricht bei 301 ab; ein POST überlebt eine Weiterleitung ohnehin nicht
    path("mcp", _McpNoSlash.as_view(), name="mcp-noslash"),
    path("mcp/verein", _McpClubNoSlash.as_view(), name="mcp-club-noslash"),
    path(
        "mcp/oauth/.well-known/oauth-authorization-server",
        oauth_views.ServerMetadataView.as_view(),
        name="mcp-oauth-metadata",
    ),
    path(
        "mcp/oauth/.well-known/openid-configuration",
        oauth_views.ServerMetadataView.as_view(),
        name="mcp-oauth-openid",
    ),
    path("mcp/oauth/resource", oauth_views.ResourceMetadataView.as_view(), name="mcp-resource"),
    path("mcp/oauth/register", oauth_views.RegisterView.as_view(), name="mcp-register"),
    path("mcp/oauth/token", oauth_views.TokenView.as_view(), name="mcp-token"),
    path("mcp/oauth/revoke", oauth_views.RevokeView.as_view(), name="mcp-revoke"),
    path("mcp/oauth/authorize/", oauth_views.AuthorizeView.as_view(), name="mcp-authorize"),
    path("me/mcp/", oauth_views.MyConnectionsView.as_view(), name="my-mcp"),
    path(
        "me/mcp/<int:pk>/",
        oauth_views.MyConnectionDetailView.as_view(),
        name="my-mcp-connection",
    ),
]

# Unter der Wurzel der Adresse (RFC 8414, RFC 9728); Caddy leitet sie ans Backend.
# Nicht im OpenAPI-Schema: dieselben Antworten stehen dort unter /api/mcp/oauth/.


@extend_schema(exclude=True)
class _RootResource(oauth_views.ResourceMetadataView):
    pass


@extend_schema(exclude=True)
class _RootServer(oauth_views.ServerMetadataView):
    pass


root_patterns = [
    re_path(
        r"^\.well-known/oauth-protected-resource(?:/api/mcp/verein/?)?$",
        _RootResource.as_view(),
        name="mcp-resource-wellknown",
    ),
    re_path(
        r"^\.well-known/(?:oauth-authorization-server|openid-configuration)(?:/api/mcp/oauth)?$",
        _RootServer.as_view(),
        name="mcp-oauth-wellknown",
    ),
]
