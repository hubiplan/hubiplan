"""Pfade eines abgeschalteten Moduls antworten mit 404.

Die Rechte von Rollen filtert schon der Rechtekatalog nach Modulen (access/catalog.py). Wo
keine Rollenrechte greifen (Mitgliederbereich, Seiten mit „jede Rolle liest“, Module ohne
eigenen Rechtebereich), bindet ``needs_module`` bzw. ``gate`` den Pfad an das Modul. Die
Einheit kommt aus ``access_id`` (Mitgliederbereich), ``org_id`` oder ``dept_id``.
"""

from __future__ import annotations

from functools import wraps

from django.http import JsonResponse
from django.urls import URLPattern
from django.utils.translation import gettext

from .modules import module_on


def _unit_of(kwargs):
    from core.tenancy import rls_bypass
    from organizations.models import Organization
    from portal.models import PortalAccess

    with rls_bypass():
        if "access_id" in kwargs:
            access = (
                PortalAccess.objects.select_related("organization")
                .filter(pk=kwargs["access_id"])
                .first()
            )
            return access.organization if access else None
        pk = kwargs.get("org_id", kwargs.get("dept_id"))
        if pk is None:
            return None
        return Organization.objects.select_related("organization").filter(pk=pk).first()


def needs_module(module: str, view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not module_on(_unit_of(kwargs), module):
            return JsonResponse({"detail": gettext("Nicht gefunden.")}, status=404)
        return view(request, *args, **kwargs)

    return wrapped


def gate(module: str, patterns):
    """Alle Pfade einer Liste an ein Modul binden."""
    result = []
    for p in patterns:
        if isinstance(p, URLPattern):
            p = URLPattern(p.pattern, needs_module(module, p.callback), p.default_args, p.name)
        result.append(p)
    return result


def gate_names(module: str, patterns, prefix: str | tuple[str, ...]):
    """Nur die Pfade, deren Name mit ``prefix`` (oder einem davon) beginnt, an ein Modul binden."""
    result = []
    for p in patterns:
        if isinstance(p, URLPattern) and (p.name or "").startswith(prefix):
            p = URLPattern(p.pattern, needs_module(module, p.callback), p.default_args, p.name)
        result.append(p)
    return result
