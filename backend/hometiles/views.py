"""Schnittstelle der Kacheln: ``/api/orgs/<Einheit>/home-tiles/`` (Verwaltung, auch in der App
unter ``/api/app/v1/admin/u/<Einheit>/home-tiles/``) und ``/api/portal/<Zugang>/home-tiles/``
(Mitglied, Browser und App mit Geräteschlüssel).

GET liefert alle Kacheln, die die Person haben darf, in fester Reihenfolge::

    {"scope": "o12", "tiles": [{"key", "title", "description", "state": "auto|on|off",
      "urgent", "default_on", "shown", "content": {"figures", "rows", "text", "link", "link_label",
      "reason"} | null}]}

PUT ``{"key": …, "state": "auto|on|off"}`` speichert die Auswahl einer Kachel. Teil der
App-Schnittstelle: Felder nur abwärtskompatibel ändern.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api_base import OrgScopedMixin
from core.tenancy import scope_of, set_rls, user_view

from . import org_tiles, portal_tiles
from .base import STATES, run, set_state


class StateSerializer(serializers.Serializer):
    key = serializers.RegexField(r"^[a-z0-9_-]{1,40}$")
    state = serializers.ChoiceField(choices=STATES)


class _Base(APIView):
    tiles: list = []

    def context(self):
        raise NotImplementedError

    def scope(self) -> str:
        raise NotImplementedError

    def payload(self, request) -> dict:
        keys = request.query_params.get("keys")
        wanted = {k for k in keys.split(",") if k} if keys else None
        return {
            "scope": self.scope(),
            "tiles": run(self.tiles, self.context(), request.user, self.scope(), wanted),
        }

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(responses=dict)
    def get(self, request, **kwargs):
        return Response(self.payload(request))

    @extend_schema(request=StateSerializer, responses=dict)
    def put(self, request, **kwargs):
        data = StateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        key = data.validated_data["key"]
        ctx = self.context()
        if not any(t.key == key and t.available(ctx) for t in self.tiles):
            raise NotFound()
        set_state(request.user, self.scope(), key, data.validated_data["state"])
        return Response(self.payload(request))


class OrgHomeTilesView(OrgScopedMixin, _Base):
    """Kacheln der Verwaltung einer Einheit (Vorstand, Kasse, Schriftführung)."""

    tiles = org_tiles.TILES

    def context(self):
        return org_tiles.OrgContext(self.org, self.org_permissions, self.request.user)

    def scope(self) -> str:
        return f"o{self.org.pk}"


class PortalHomeTilesView(_Base):
    """Kacheln im Mitgliederbereich eines Zugangs."""

    tiles = portal_tiles.TILES

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        from portal.views import _portal_access

        with user_view(request.user.pk):
            access = _portal_access(request.user, kwargs["access_id"])
        set_rls(access.organization_id, request.user.pk, scope_id=scope_of(access.organization_id))
        self.access = access

    def context(self):
        return portal_tiles.PortalContext(self.access, self.request.user)

    def scope(self) -> str:
        return f"p{self.access.pk}"
