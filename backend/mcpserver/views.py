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
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.negotiation import BaseContentNegotiation
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.views import APIView

from core.ratelimit import client_ip, too_many

from . import protocol

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

        def link(slug: str) -> str:
            return request.build_absolute_uri(f"/hilfe/{slug}")

        answer = protocol.handle(message, link)
        if answer is None:
            return HttpResponse(status=202)
        return _json(answer)
