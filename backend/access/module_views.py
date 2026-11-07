"""Einstellungen › Module: Die Einheit schaltet freigegebene Module ein oder aus (M3).

Die Plattform gibt frei (``released_modules``), die Einheit schaltet ein (``enabled_modules``).
Ausschalten löscht nichts: Daten und Rechte ruhen, öffentliche Teile gehen offline.
"""

from __future__ import annotations

from django.db import transaction
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import record
from core.api_base import OrgScopedMixin

from .catalog import SETTINGS_EDIT, SETTINGS_VIEW
from .modules import GROUPS, MODULES, ModuleChoiceError, apply_enabled, released_of


def module_states(org) -> list[dict]:
    """Gruppen mit den Modulen, die es für diese Art von Einheit gibt, samt Zustand."""
    released = released_of(org)
    enabled = set(org.enabled_modules or [])
    groups = []
    for group in GROUPS:
        modules = []
        for m in MODULES:
            if m.group != group.id or org.type not in m.org_types:
                continue
            modules.append(
                {
                    "id": m.id,
                    "label": gettext(m.label),
                    "description": gettext(m.description),
                    "requires": list(m.requires),
                    "requires_any": list(m.requires_any),
                    "released": m.id in released,
                    "enabled": m.id in enabled,
                    # Eingeschaltete Module, die dieses voraussetzen
                    "needed_by": sorted(
                        d.id
                        for d in MODULES
                        if d.id in enabled and (m.id in d.requires or m.id in d.requires_any)
                    ),
                }
            )
        if modules:
            groups.append({"id": group.id, "label": gettext(group.label), "modules": modules})
    return groups


class OrgModulesView(OrgScopedMixin, APIView):
    """GET: Module der Einheit. PATCH {enabled: [...], dry_run}: ein- und ausschalten."""

    read_permission = SETTINGS_VIEW
    write_permission = SETTINGS_EDIT
    allowed_org_types = ("federation", "club")

    def get(self, request, org_id: int):
        return Response({"groups": module_states(self.org)})

    @transaction.atomic
    def patch(self, request, org_id: int):
        wanted = request.data.get("enabled")
        if not isinstance(wanted, list) or not all(isinstance(m, str) for m in wanted):
            raise serializers.ValidationError(
                {"enabled": gettext("Bitte eine Liste von Modulen angeben.")}
            )
        org = self.org
        before = set(org.enabled_modules or [])
        try:
            apply_enabled(org, wanted)
        except ModuleChoiceError as exc:
            raise serializers.ValidationError({"enabled": str(exc)}) from exc
        after = set(org.enabled_modules)
        changes = {"on": sorted(after - before), "off": sorted(before - after)}
        if request.data.get("dry_run"):
            org.refresh_from_db()
            return Response({"changes": changes})
        if after != before:
            record(
                org,
                request.user,
                "update",
                org,
                {"Module": [", ".join(sorted(before)), ", ".join(sorted(after))]},
            )
            org.save(update_fields=["enabled_modules", "released_modules"])
        return Response({"changes": changes, "groups": module_states(org)})
