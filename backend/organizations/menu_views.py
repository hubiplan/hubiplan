"""Schnittstelle ``/api/orgs/<Einheit>/menu-layout/``: Anordnung des Menüs lesen und ändern.

GET liefert ``{"layout": … | null, "standard": {...}, "can_undo": bool, "owned": bool}``.
PUT ``{"layout": … | null}`` speichert (null = Standard wiederherstellen), POST ``undo/``
stellt die vorige Anordnung wieder her. Schreiben braucht ``settings.edit``; Untereinheiten
übernehmen die Anordnung ihres Vereins und ändern sie nicht selbst.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import record
from core.api_base import OrgScopedMixin

from . import menu_layout

SETTINGS_EDIT = "settings.edit"


def _payload(org) -> dict:
    own = menu_layout.owner(org) == org
    return {
        "layout": menu_layout.effective(org),
        "standard": menu_layout.standard(),
        "can_undo": own and bool(org.menu_layout_history),
        "owned": own,
        "max_areas": menu_layout.MAX_AREAS,
    }


class MenuLayoutView(OrgScopedMixin, APIView):
    read_permission = None
    write_permission = SETTINGS_EDIT

    def _check_owner(self):
        if menu_layout.owner(self.org) != self.org:
            raise PermissionDenied("Untereinheiten übernehmen das Menü ihres Vereins.")

    @extend_schema(responses=dict)
    def get(self, request, **kwargs):
        return Response(_payload(self.org))

    @extend_schema(request=dict, responses=dict)
    def put(self, request, **kwargs):
        self._check_owner()
        before = self.org.menu_layout
        menu_layout.save(self.org, request.data.get("layout"), request.user)
        if before != self.org.menu_layout:
            record(
                self.org,
                request.user,
                "update",
                self.org,
                {
                    "Anordnung des Menüs": {
                        "before": "eigene" if before else "Standard",
                        "after": "eigene" if self.org.menu_layout else "Standard",
                    }
                },
            )
        return Response(_payload(self.org))


class MenuLayoutUndoView(OrgScopedMixin, APIView):
    read_permission = SETTINGS_EDIT
    write_permission = SETTINGS_EDIT

    @extend_schema(request=None, responses=dict)
    def post(self, request, **kwargs):
        if menu_layout.owner(self.org) != self.org:
            raise PermissionDenied("Untereinheiten übernehmen das Menü ihres Vereins.")
        menu_layout.undo(self.org)
        record(
            self.org,
            request.user,
            "update",
            self.org,
            {"Anordnung des Menüs": {"before": "", "after": "vorige wiederhergestellt"}},
        )
        return Response(_payload(self.org))
