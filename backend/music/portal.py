"""Mitglieder sehen und beantworten ausschließlich ihre eigenen Einteilungen."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import record
from core.tenancy import tenant_context
from portal.views import _portal_access

from .models import Assignment


class OwnAssignments(APIView):
    def rows(self, request, access_id):
        access = _portal_access(request.user, access_id)
        if "music" not in access.organization.enabled_modules:
            return access, Assignment.objects.none()
        return access, Assignment.objects.filter(
            organization=access.organization,
            musician__membership_id=access.membership_id,
            musician__active=True,
        ).select_related("performance__event", "position")

    def get(self, request, access_id):
        access, rows = self.rows(request, access_id)
        with tenant_context(access.organization_id, request.user.pk):
            return Response(
                [
                    {
                        "id": row.pk,
                        "title": row.performance.event.title,
                        "starts_at": row.performance.event.starts_at,
                        "location": row.performance.event.location,
                        "meeting_at": row.performance.meeting_at,
                        "meeting_place": row.performance.meeting_place,
                        "uniform": row.performance.uniform,
                        "cancelled": row.performance.event.is_cancelled,
                        "instrument": row.position.instrument,
                        "register": row.position.register,
                        "status": row.status,
                    }
                    for row in rows
                ]
            )

    @transaction.atomic
    def post(self, request, access_id):
        access, rows = self.rows(request, access_id)
        with tenant_context(access.organization_id, request.user.pk):
            row = get_object_or_404(rows.select_for_update(of=("self",)), pk=request.data.get("id"))
            field = serializers.ChoiceField(choices=["accepted", "declined"])
            previous = row.status
            row.status = field.run_validation(request.data.get("status"))
            row.save(update_fields=["status"])
            record(
                access.organization,
                request.user,
                "update",
                row,
                {"Rückmeldung": [previous, row.status]},
            )
            return Response({"status": row.status})
