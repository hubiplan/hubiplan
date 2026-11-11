"""Adresse der KI-Schnittstelle: ``/api/mcp/`` (docs/mcp.md).

Stufe 0: ohne Anmeldung, nur die Hilfe. Der Betreiber schaltet sie mit
``HUBIPLAN_MCP_HILFE=false`` ab. Gegen DNS-Rebinding (MCP-Spezifikation) werden
Anfragen mit fremdem ``Origin`` abgelehnt; Browser-Seiten fremder Adressen kommen
also nicht hinein, KI-Dienste schicken keinen ``Origin``.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.utils.translation import gettext as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.negotiation import BaseContentNegotiation
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.views import APIView

from core.ratelimit import client_ip, too_many

from . import protocol
from .tools import Context

MAX_BODY = 64 * 1024
RATE_LIMIT = 120  # Anfragen je Minute und Adresse


def _json(data, status: int = 200) -> JsonResponse:
    response = JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


def _origin_ok(request) -> bool:
    origin = request.headers.get("Origin")
    if not origin:
        return True
    return (urlsplit(origin).netloc or "").lower() == request.get_host().lower()


def help_link(request):
    def link(slug: str) -> str:
        return request.build_absolute_uri(f"/hilfe/{slug}")

    return link


class _AlwaysJson(BaseContentNegotiation):
    """MCP-Clients schicken ``Accept: application/json, text/event-stream``; wir
    antworten immer mit JSON, auch wenn ein Client nur den Ereignisstrom nennt."""

    def select_parser(self, request, parsers):
        return parsers[0] if parsers else None

    def select_renderer(self, request, renderers, format_suffix=None):
        return renderers[0], renderers[0].media_type


class McpView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    renderer_classes = [JSONRenderer]
    content_negotiation_class = _AlwaysJson

    def initial(self, request, *args, **kwargs):
        if not settings.MCP_HILFE_ENABLED:
            raise Http404
        super().initial(request, *args, **kwargs)

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT, 202: None},
        description=(
            "KI-Schnittstelle nach dem Model Context Protocol (JSON-RPC 2.0, Streamable HTTP "
            "ohne Ereignisstrom). Stufe 0: Werkzeuge zur HUBIplan-Hilfe, ohne Anmeldung."
        ),
    )
    def post(self, request):
        if not _origin_ok(request):
            return HttpResponse(status=403)
        version = request.headers.get("MCP-Protocol-Version")
        if version and version not in protocol.PROTOCOL_VERSIONS:
            return _json(
                protocol.error(None, protocol.INVALID_REQUEST, "Unsupported protocol version"), 400
            )
        if too_many(f"mcp:{client_ip(request)}", RATE_LIMIT, 60):
            return _json(protocol.error(None, protocol.INVALID_REQUEST, "Too many requests"), 429)
        body = request.body
        if len(body) > MAX_BODY:
            return _json(protocol.error(None, protocol.INVALID_REQUEST, "Request too large"), 413)
        try:
            message = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return _json(protocol.error(None, protocol.PARSE_ERROR, "Parse error"), 400)

        answer = protocol.handle(message, Context(link=help_link(request)))
        if answer is None:
            return HttpResponse(status=202)
        return _json(answer)


# --- Stufe 1a: mit Anmeldung, für die verbundene Einheit (/api/mcp/verein/) ---

GRANT_LIMIT = 300  # Werkzeugaufrufe je Stunde und Verbindung


def _unauthorized(request, description: str = "") -> JsonResponse:
    from . import oauth

    body = protocol.error(None, protocol.INVALID_REQUEST, "Unauthorized")
    response = _json(body, 401)
    header = f'Bearer resource_metadata="{oauth.resource_metadata_url(request)}"'
    if description:
        header += ', error="invalid_token"'
    response["WWW-Authenticate"] = header
    return response


def club_server():
    from . import club

    return protocol.Server(
        name="hubiplan-verein",
        title=lambda: _("HUBIplan"),
        instructions=lambda: _(
            "HUBIplan, eine freie Vereinsverwaltung. Diese Verbindung gilt für genau eine "
            "Einheit und darf nie mehr als die Person, die sie erlaubt hat. Die Webseite lässt "
            "sich lesen und als Entwurf bearbeiten (Texte, Inhalte der Startseite, neue "
            "Textseiten). Veröffentlichen, Zustand, Domains und Gestaltung gibt es hier nicht; "
            "das macht ein Mensch in HUBIplan. Nach Änderungen webseite_vorschau anbieten. "
            "Für Fragen zur Bedienung die Hilfe-Werkzeuge nutzen."
        ),
        tools=club.tools_for,
    )


class McpClubView(APIView):
    """KI-Schnittstelle mit Anmeldung (Bearer ``hpm_…``, OAuth 2.1, docs/mcp.md)."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    renderer_classes = [JSONRenderer]
    content_negotiation_class = _AlwaysJson

    def initial(self, request, *args, **kwargs):
        if not settings.MCP_ENABLED:
            raise Http404
        super().initial(request, *args, **kwargs)

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT, 202: None, 401: OpenApiTypes.OBJECT},
        description=(
            "KI-Schnittstelle nach dem Model Context Protocol mit Anmeldung (OAuth 2.1): "
            "Hilfe und Webseite der verbundenen Einheit (lesen, Entwurf bearbeiten)."
        ),
    )
    def post(self, request):
        from audit.log import current_via
        from changes import tracking
        from core.i18n import activate_for
        from core.tenancy import set_rls

        from .auth import TokenInvalid, bearer, find_grant
        from .club import ClubContext

        if not _origin_ok(request):
            return HttpResponse(status=403)
        token = bearer(request)
        if not token:
            return _unauthorized(request)
        try:
            grant = find_grant(token)
        except TokenInvalid as exc:
            return _unauthorized(request, exc.description or "invalid")
        version = request.headers.get("MCP-Protocol-Version")
        if version and version not in protocol.PROTOCOL_VERSIONS:
            return _json(
                protocol.error(None, protocol.INVALID_REQUEST, "Unsupported protocol version"), 400
            )
        if too_many(f"mcp:grant:{grant.pk}", GRANT_LIMIT, 3600):
            return _json(protocol.error(None, protocol.INVALID_REQUEST, "Too many requests"), 429)
        body = request.body
        if len(body) > MAX_BODY:
            return _json(protocol.error(None, protocol.INVALID_REQUEST, "Request too large"), 413)
        try:
            message = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return _json(protocol.error(None, protocol.PARSE_ERROR, "Parse error"), 400)
        user = grant.user
        set_rls(None, user.pk)
        activate_for(request, user)
        # Änderungspaket gehört der Person (Rückgängig), das Protokoll nennt den Assistenten
        ctx = tracking.active()
        if ctx is not None:
            ctx.user_id = user.pk
        via = current_via.set(f"KI-Assistent ({grant.client.name})"[:100])
        try:
            answer = protocol.handle(
                message,
                ClubContext(link=help_link(request), request=request, grant=grant),
                club_server(),
            )
        finally:
            current_via.reset(via)
        if answer is None:
            return HttpResponse(status=202)
        return _json(answer)
