"""Versammlungen im Mitgliederbereich (Schritt V5).

Stimmberechtigte sehen anstehende Versammlungen, zu denen eingeladen ist, mit Tagesordnung
und freigegebene Protokolle, wenn die Art sie für alle Stimmberechtigten bestimmt.
Vorstands- und Gremienprotokolle bleiben den Rollen mit Leserecht vorbehalten.
"""

from __future__ import annotations

import datetime

from django.http import FileResponse
from django.utils import timezone
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from core.tenancy import scope_of, set_rls, user_view

from . import services
from .models import Meeting, MeetingKind

# Protokolle der letzten Jahre; ältere stehen in der Dokumentenablage
YEARS_BACK = 5


def portal_access(user, access_id):
    from portal.views import _portal_access

    with user_view(user.pk):
        access = _portal_access(user, access_id)
    set_rls(access.organization_id, user.pk, scope_id=scope_of(access.organization_id))
    if "meetings" not in (access.organization.enabled_modules or []):
        raise NotFound()
    if not access.membership.current_period():
        raise NotFound()
    return access


def is_voter(meeting: Meeting, membership_id: int) -> bool:
    return services.voters(meeting).filter(pk=membership_id).exists()


def visible(access) -> tuple[list[Meeting], list[Meeting]]:
    """Anstehende Versammlungen mit Einladung und freigegebene Protokolle des Mitglieds."""
    now = timezone.now()
    base = Meeting.objects.filter(organization=access.organization).select_related(
        "event", "kind", "organization", "department"
    )
    upcoming = [
        m
        for m in base.filter(
            status=Meeting.Status.INVITED, event__ends_at__gte=now - datetime.timedelta(hours=12)
        ).order_by("event__starts_at")[:20]
        if is_voter(m, access.membership_id)
    ]
    since = now - datetime.timedelta(days=365 * YEARS_BACK)
    minutes = [
        m
        for m in base.filter(
            status=Meeting.Status.DONE,
            kind__minutes_for=MeetingKind.MinutesFor.VOTERS,
            event__starts_at__gte=since,
        ).order_by("-event__starts_at")[:50]
        if is_voter(m, access.membership_id)
    ]
    return upcoming, minutes


def unit_name(meeting: Meeting) -> str:
    return meeting.department.name if meeting.department_id else ""


class Base(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.access = portal_access(request.user, kwargs["access_id"])

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class ListView(Base):
    def get(self, request, **kwargs):
        upcoming, minutes = visible(self.access)
        return Response(
            {
                "upcoming": [
                    {
                        "id": m.pk,
                        "title": m.event.title,
                        "kind_name": m.kind.name,
                        "unit": unit_name(m),
                        "starts_at": m.event.starts_at,
                        "location": m.event.location,
                        "address": m.event.address,
                        "agenda": [
                            {
                                "position": item.position,
                                "title": item.title,
                                "description": item.description,
                            }
                            for item in m.agenda.all()
                        ],
                    }
                    for m in upcoming
                ],
                "minutes": [
                    {
                        "id": m.pk,
                        "title": m.event.title,
                        "kind_name": m.kind.name,
                        "unit": unit_name(m),
                        "starts_at": m.event.starts_at,
                    }
                    for m in minutes
                    if m.minutes_versions.exists()
                ],
            }
        )


class MinutesView(Base):
    def get(self, request, pk, **kwargs):
        _upcoming, minutes = visible(self.access)
        meeting = next((m for m in minutes if m.pk == pk), None)
        if meeting is None:
            raise NotFound()
        released = meeting.minutes_versions.first()
        if released is None:
            raise NotFound()
        name = f"protokoll-{timezone.localtime(meeting.event.starts_at):%Y-%m-%d}.pdf"
        response = FileResponse(
            released.file.open("rb"), content_type="application/pdf", filename=name
        )
        response["X-Content-Type-Options"] = "nosniff"
        return response
