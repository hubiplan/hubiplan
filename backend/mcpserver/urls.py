"""Adressen der KI-Schnittstelle (docs/mcp.md)."""

from django.urls import path, re_path

from . import oauth_views
from .views import McpClubView, McpView

api_patterns = [
    # Stufe 0: nur Hilfe, ohne Anmeldung
    path("mcp/", McpView.as_view(), name="mcp"),
    # Stufe 1a: mit Anmeldung, Webseite der verbundenen Einheit (W1)
    path("mcp/verein/", McpClubView.as_view(), name="mcp-club"),
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

# Unter der Wurzel der Adresse (RFC 8414, RFC 9728); Caddy leitet sie ans Backend
root_patterns = [
    re_path(
        r"^\.well-known/oauth-protected-resource(?:/api/mcp/verein/?)?$",
        oauth_views.ResourceMetadataView.as_view(),
        name="mcp-resource-wellknown",
    ),
    re_path(
        r"^\.well-known/(?:oauth-authorization-server|openid-configuration)(?:/api/mcp/oauth)?$",
        oauth_views.ServerMetadataView.as_view(),
        name="mcp-oauth-wellknown",
    ),
]
