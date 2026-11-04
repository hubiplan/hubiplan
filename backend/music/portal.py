"""Mitglieder sehen und beantworten ausschließlich ihre eigenen Einteilungen."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import record
from core.tenancy import tenant_context
from portal.views import _portal_access

from .availability import Availability, ensure_performance, performance_interval
from .models import Assignment, Musician, MusicianClaim, Performance
from .settlement import personal_claim


def own_program(performance):
    return [
        {
            "title": e.arrangement.piece.title if e.arrangement_id else "",
            "kind": e.kind,
            "duration_seconds": e.duration_seconds
            if e.duration_seconds is not None
            else e.arrangement.duration_seconds
            if e.arrangement_id
            else 0,
        }
        for e in performance.program_entries.select_related("arrangement__piece")
    ]


def own_conflicts(access, row):
    start, end = performance_interval(row.performance)
    if end <= timezone.now():
        return []
    return Availability(
        access.organization, [row.musician], row.performance.event, start, end
    ).reasons(row.musician)


class OwnAssignments(APIView):
    def rows(self, request, access_id):
        access = _portal_access(request.user, access_id)
        if "music" not in access.organization.enabled_modules:
            return access, Assignment.objects.none()
        return access, Assignment.objects.filter(
            organization=access.organization,
            musician__membership_id=access.membership_id,
            musician__active=True,
        ).select_related("performance__event", "position", "musician")

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
                        "availability": own_conflicts(access, row),
                        "program": own_program(row.performance),
                        "settlement": next(
                            (
                                personal_claim(c)
                                for c in MusicianClaim.objects.filter(
                                    assignment=row, status="approved"
                                )
                            ),
                            None,
                        ),
                    }
                    for row in rows
                ]
            )

    @transaction.atomic
    def post(self, request, access_id):
        access, rows = self.rows(request, access_id)
        with tenant_context(access.organization_id, request.user.pk):
            pk = serializers.IntegerField(min_value=1).run_validation(request.data.get("id"))
            target = get_object_or_404(rows, pk=pk)
            Performance.objects.select_for_update().get(pk=target.performance_id)
            Musician.objects.select_for_update().get(pk=target.musician_id)
            row = get_object_or_404(rows.select_for_update(of=("self",)), pk=pk)
            field = serializers.ChoiceField(choices=["accepted", "declined"])
            previous = row.status
            row.status = field.run_validation(request.data.get("status"))
            if row.status == "accepted":
                ensure_performance(row.musician, row.performance)
            row.save(update_fields=["status"])
            record(
                access.organization,
                request.user,
                "update",
                row,
                {"Rückmeldung": [previous, row.status]},
            )
            return Response({"status": row.status})
