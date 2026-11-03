"""Local, audited approval for guest results; never accepted from peers/offline sync."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from access.catalog import COMPETITIONS_MANAGE, PEERING_MANAGE
from access.permissions import permissions_in
from audit.log import record
from peering.models import Coupling

from .models import Starter
from .views import _Mixin


class OwnershipInput(serializers.Serializer):
    starter = serializers.IntegerField(min_value=1, max_value=2**63 - 1)
    coupling = serializers.IntegerField(min_value=1, max_value=2**63 - 1, allow_null=True)


class ResultOwnershipView(_Mixin, APIView):
    def check_rights(self):
        rights = permissions_in(self.request.user, self.org)
        if not {COMPETITIONS_MANAGE, PEERING_MANAGE} <= rights:
            raise PermissionDenied(
                gettext("Für die Ergebnisfreigabe sind Wettbewerb und Verbund zu verwalten.")
            )

    def partners(self):
        return Coupling.objects.filter(
            local_unit=self.org, direction=Coupling.Direction.CHILD, state=Coupling.State.ACTIVE
        )

    def get(self, request, org_id, competition_id):
        self.check_rights()
        comp = self.competition(competition_id)
        return Response(
            {
                "partners": [
                    {"id": c.pk, "name": c.remote_unit.name}
                    for c in self.partners().select_related("remote_unit")
                ],
                "starters": [
                    {"id": s.pk, "name": s.name, "club": s.club, "coupling": s.result_coupling_id}
                    for s in comp.starters.filter(unit__isnull=True).order_by("name", "pk")
                ],
            }
        )

    @transaction.atomic
    def post(self, request, org_id, competition_id):
        self.check_rights()
        incoming = OwnershipInput(data=request.data)
        incoming.is_valid(raise_exception=True)
        comp = self.competition(competition_id)
        if not comp.own:
            raise ValidationError(gettext("Nur eigene Wettbewerbe können Ergebnisse freigeben."))
        starter = get_object_or_404(
            Starter.objects.select_for_update(),
            competition=comp,
            organization=self.org,
            pk=incoming.validated_data["starter"],
        )
        if starter.unit_id:
            raise ValidationError(
                gettext("Dieser Starter ist bereits einer Untereinheit zugeordnet.")
            )
        raw = incoming.validated_data["coupling"]
        coupling = get_object_or_404(self.partners().select_for_update(), pk=raw) if raw else None
        before = starter.result_coupling_id
        starter.result_coupling = coupling
        starter.save(update_fields=["result_coupling", "updated_at"])
        record(
            self.org,
            request.user,
            "update",
            starter,
            {"result_coupling": [before, coupling.pk if coupling else None]},
        )
        return Response({"ok": True})
