"""Persönliche Proben und Noten unter den bestehenden Dokumentenfreigaben."""

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseNotModified
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from core.tenancy import tenant_context
from documents import services as documents
from documents.models import Document
from documents.views import file_response
from events import recurrence
from members.models import DepartmentMembership
from organizations.tree import with_ancestors
from portal.views import _portal_access

from .availability import Availability, interval
from .models import (
    Musician,
    Rehearsal,
    RehearsalInvitation,
    ScoreDocument,
    ScoreFolder,
    ScoreFolderItem,
    ScoreLoan,
)
from .practice import loan_data, save_response, window
from .practice_programs import program_for, with_programs
from .scores import voice


def own_musician(access):
    if "music" not in access.organization.enabled_modules:
        return None
    if not access.membership.current_period() or access.membership.purged_at:
        return None
    return Musician.objects.filter(
        organization=access.organization, membership_id=access.membership_id, active=True
    ).first()


def practice_rows(musician, include_availability=False):
    if "events" not in musician.organization.enabled_modules:
        return []
    invitations = list(
        musician.rehearsalinvitation_set.filter(active=True).prefetch_related("responses")
    )
    rehearsals = {
        r.pk: r
        for r in with_programs(
            Rehearsal.objects.filter(pk__in=[i.rehearsal_id for i in invitations]).select_related(
                "event"
            )
        )
    }
    rows = []
    for invite in invitations:
        rehearsal = rehearsals[invite.rehearsal_id]
        responses = {r.original_start: r.status for r in invite.responses.all()}
        for o in recurrence.occurrences([rehearsal.event], *window()):
            rows.append(
                {
                    "id": invite.pk,
                    "title": rehearsal.event.title,
                    "original_start": o.original_start,
                    "starts_at": o.starts_at,
                    "ends_at": o.ends_at,
                    "location": rehearsal.event.location,
                    **program_for(rehearsal, o.original_start),
                    "cancelled": o.is_cancelled,
                    "can_respond": not o.is_cancelled and o.starts_at > timezone.now(),
                    "status": responses.get(o.original_start, "pending"),
                    **(
                        {
                            "availability": Availability(
                                musician.organization,
                                [musician],
                                rehearsal.event,
                                *interval(rehearsal.event, o.starts_at, o.ends_at),
                            ).reasons(musician)
                        }
                        if include_availability
                        else {}
                    ),
                }
            )
    return sorted(rows, key=lambda r: r["starts_at"])


def member_departments(access):
    today = timezone.localdate()
    return list(
        DepartmentMembership.objects.filter(
            membership_id=access.membership_id, valid_from__lte=today
        )
        .filter(Q(valid_until=None) | Q(valid_until__gte=today))
        .values_list("department_id", flat=True)
    )


def visible_folders(access, musician, departments=None):
    """Feste Notenmappen (Marschbuch, Repertoire) für diesen Musiker."""
    if not musician or "scores" not in access.organization.enabled_modules:
        return ScoreFolder.objects.none()
    if departments is None:
        departments = member_departments(access)
    units = with_ancestors(access.organization_id, departments) | set(departments)
    return (
        ScoreFolder.objects.filter(organization=access.organization, active=True)
        .filter(Q(units=None) | Q(units__department_id__in=units))
        .distinct()
    )


def musician_voices(musician):
    voices = {voice(s.instrument, s.register) for s in musician.skills.all()}
    voices.update(
        voice(a.position.instrument, a.position.register)
        for a in musician.assignment_set.select_related("position")
    )
    return voices


def accessible_scores(access, musician, rehearsals=None):
    if not musician:
        return ScoreDocument.objects.none()
    departments = member_departments(access)
    folders = documents.member_viewer(access.organization, departments).all_folders()
    docs = Document.objects.filter(
        organization=access.organization, folder__in=folders, deleted_at=None
    )
    arrangements = set()
    if "events" in access.organization.enabled_modules:
        arrangements.update(
            musician.assignment_set.exclude(status="declined")
            .filter(performance__event__is_cancelled=False)
            .values_list("performance__program_entries__arrangement_id", flat=True)
        )
        rows = practice_rows(musician) if rehearsals is None else rehearsals
        arrangements.update(
            item["arrangement"]
            for row in rows
            if not row["cancelled"] and row["status"] != "declined"
            for item in row["items"]
        )
    arrangements.update(
        ScoreFolderItem.objects.filter(
            folder__in=visible_folders(access, musician, departments), arrangement__active=True
        ).values_list("arrangement_id", flat=True)
    )
    arrangements.discard(None)
    voices = musician_voices(musician)
    candidates = ScoreDocument.objects.filter(
        organization=access.organization, arrangement_id__in=arrangements, document__in=docs
    ).select_related("part", "document", "arrangement__piece")
    ids = [
        r.pk
        for r in candidates
        if r.part_id is None or voice(r.part.instrument, r.part.register) in voices
    ]
    return candidates.filter(pk__in=ids).order_by("arrangement_id", "position", "pk")


def score_data(access, musician, rehearsals=None):
    return [
        {
            "id": s.pk,
            "arrangement": s.arrangement_id,
            "title": s.document.title,
            "piece": s.arrangement.piece.title,
            "usage_note": s.usage_note,
            "url": f"/api/portal/{access.pk}/music/files/{s.pk}/",
        }
        for s in accessible_scores(access, musician, rehearsals)
    ]


class OwnPractice(APIView):
    def get(self, request, access_id):
        access = _portal_access(request.user, access_id)
        with tenant_context(access.organization_id, request.user.pk):
            musician = own_musician(access)
            if not musician:
                return Response({"rehearsals": [], "scores": [], "loans": []})
            rows = practice_rows(musician, include_availability=True)
            scores = score_data(access, musician, rows)
            for row in rows:
                arrangements = {i["arrangement"] for i in row["items"]}
                row["scores"] = (
                    [s for s in scores if s["arrangement"] in arrangements]
                    if (not row["cancelled"] and row["status"] != "declined")
                    else []
                )
            return Response(
                {
                    "rehearsals": rows,
                    "scores": scores,
                    "loans": [
                        loan_data(r)
                        for r in ScoreLoan.objects.filter(musician=musician)
                        .select_related("part__arrangement__piece")
                        .order_by("-pk")
                    ],
                }
            )

    @transaction.atomic
    def post(self, request, access_id):
        access = _portal_access(request.user, access_id)
        with tenant_context(access.organization_id, request.user.pk):
            musician = own_musician(access)
            if not musician or "events" not in access.organization.enabled_modules:
                raise NotFound()
            pk = serializers.IntegerField(min_value=1).run_validation(request.data.get("id"))
            invite = get_object_or_404(
                RehearsalInvitation.objects.select_for_update(),
                pk=pk,
                musician=musician,
                active=True,
            )
            save_response(invite, request.data, request.user)
            return Response({"ok": True})


class OwnScoreFile(APIView):
    def get(self, request, access_id, pk):
        access = _portal_access(request.user, access_id)
        with tenant_context(access.organization_id, request.user.pk):
            musician = own_musician(access)
            link = get_object_or_404(accessible_scores(access, musician), pk=pk)
            version = link.document.versions.order_by("-uploaded_at", "-pk").first()
            if not version:
                raise NotFound()
            return versioned_file(request, version)


def versioned_file(request, version):
    """Datei mit Fassungskennung; die App lädt nur neu, wenn sich die Fassung geändert hat."""
    etag = f'"v{version.pk}"'
    if etag in [t.strip() for t in request.headers.get("If-None-Match", "").split(",")]:
        response = HttpResponseNotModified()
    else:
        response = file_response(request, version)
    response["ETag"] = etag
    return response
