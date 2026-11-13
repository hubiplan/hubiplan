"""Schnittstellen der Anmeldung für KI-Assistenten (Stufe 1a, docs/mcp.md).

Öffentlich (für den Assistenten): Beschreibungen unter ``/.well-known/…`` und
``/api/mcp/oauth/…``, ``register``, ``token``, ``revoke``. Für die Seite
„KI-Assistent verbinden“: ``/api/mcp/oauth/authorize/`` (angemeldet, mit CSRF). Für
„Mein Konto“: ``/api/me/mcp/`` (eigene Verbindungen ansehen und trennen).
"""

from __future__ import annotations

from django.conf import settings
from django.http import Http404, JsonResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.authentication import SessionAuthentication
from rest_framework.parsers import FormParser, JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from changes import tracking
from core.ratelimit import TooMany, client_ip, too_many
from core.tenancy import rls_bypass

from . import oauth
from .models import McpGrant

TOKEN_RATE = (60, 60)
REGISTER_RATE = (20, 3600)


def _json(data: dict, status: int = 200, cache: str = "no-store") -> JsonResponse:
    response = JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = cache
    if cache == "no-store":
        response["Pragma"] = "no-cache"
    # Assistenten im Browser (z. B. Prüfwerkzeuge) dürfen die Beschreibungen lesen
    response["Access-Control-Allow-Origin"] = "*"
    return response


def _error(exc: oauth.OAuthError) -> JsonResponse:
    return _json(exc.body(), status=exc.status)


class _Public(APIView):
    """Für den Assistenten: ohne Anmeldung, ohne Sitzung, ohne CSRF."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def initial(self, request, *args, **kwargs):
        if not settings.MCP_ENABLED:
            raise Http404
        super().initial(request, *args, **kwargs)

    def options(self, request, *args, **kwargs):
        response = _json({}, cache="no-store")
        response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = (
            "Content-Type, Authorization, MCP-Protocol-Version"
        )
        return response


class ResourceMetadataView(_Public):
    @extend_schema(responses=OpenApiTypes.OBJECT, description="RFC 9728")
    def get(self, request, *args, **kwargs):
        return _json(oauth.resource_metadata(request), cache="public, max-age=3600")


class ServerMetadataView(_Public):
    @extend_schema(responses=OpenApiTypes.OBJECT, description="RFC 8414")
    def get(self, request, *args, **kwargs):
        return _json(oauth.server_metadata(request), cache="public, max-age=3600")


class RegisterView(_Public):
    """Selbstanmeldung eines Assistenten (RFC 7591), nur öffentliche Clients."""

    parser_classes = [JSONParser]

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        if too_many(f"mcp:register:{client_ip(request)}", *REGISTER_RATE):
            return _json({"error": "slow_down"}, status=429)
        try:
            return _json(oauth.register(request.data), status=201)
        except oauth.OAuthError as exc:
            return _error(exc)


class TokenView(_Public):
    """Code einlösen oder Schlüssel erneuern (Formular, kein JSON)."""

    parser_classes = [FormParser]

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        if too_many(f"mcp:token:{client_ip(request)}", *TOKEN_RATE):
            return _json({"error": "slow_down"}, status=429)
        try:
            return _json(oauth.token(request._request))
        except oauth.OAuthError as exc:
            return _error(exc)


class RevokeView(_Public):
    parser_classes = [FormParser]

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: None})
    def post(self, request):
        if too_many(f"mcp:token:{client_ip(request)}", *TOKEN_RATE):
            return _json({"error": "slow_down"}, status=429)
        oauth.revoke(request._request)
        return _json({})


class AuthorizeView(APIView):
    """Für die Seite „KI-Assistent verbinden“: Anfrage beschreiben bzw. zustimmen."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        if not settings.MCP_ENABLED:
            raise Http404
        super().initial(request, *args, **kwargs)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        try:
            return Response(oauth.describe(request._request, request.query_params))
        except oauth.ConsentError as exc:
            return Response({"detail": exc.message, "redirect": exc.redirect}, status=400)

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        key = f"mcp:authorize:{request.user.pk}"
        if too_many(key, 30, 600):
            raise TooMany(key)
        data = request.data if isinstance(request.data, dict) else {}
        params = data.get("params") if isinstance(data.get("params"), dict) else {}
        if data.get("deny"):
            # Abgelehnt: Assistent erfährt es über die Rückleitung
            try:
                oauth.describe(request._request, params)
            except oauth.ConsentError as exc:
                return Response({"detail": exc.message, "redirect": exc.redirect}, status=400)
            return Response({"redirect": oauth.denied(request._request, params)})
        try:
            url = oauth.authorize(request._request, params, data.get("organization"))
        except oauth.ConsentError as exc:
            return Response({"detail": exc.message, "redirect": exc.redirect}, status=400)
        return Response({"redirect": url})


def grant_data(grant: McpGrant) -> dict:
    return {
        "id": grant.pk,
        "client": grant.client.name,
        "organization": grant.organization.name,
        "scopes": oauth.scope_labels(grant.scopes),
        "created_at": grant.created_at,
        "last_used_at": grant.last_used_at,
        "expires_at": grant.expires_at,
    }


class MyConnectionsView(APIView):
    """GET: eigene Verbindungen zu KI-Assistenten (aktiv) · Mein Konto › App."""

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        grants = (
            McpGrant.objects.filter(user=request.user, revoked_at=None)
            .select_related("client", "organization")
            .order_by("-created_at")
        )
        return Response(
            {
                "enabled": bool(settings.MCP_ENABLED),
                "address": oauth.resource(request._request),
                "connections": [grant_data(g) for g in grants if g.is_active],
            }
        )


class MyConnectionDetailView(APIView):
    """DELETE: Verbindung trennen (sofort, alle Schlüssel ungültig)."""

    @extend_schema(responses={204: None})
    def delete(self, request, pk: int):
        grant = (
            McpGrant.objects.filter(user=request.user, pk=pk, revoked_at=None)
            .select_related("organization", "client")
            .first()
        )
        if grant is None:
            raise Http404
        from audit.log import record

        with tracking.suppress(), rls_bypass():
            grant.revoke("getrennt")
            record(
                grant.organization,
                request.user,
                "update",
                grant,
                {"KI-Assistent": [grant.client.name, "getrennt"]},
            )
        return Response(status=204)
