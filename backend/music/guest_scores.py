"""Explicit grants freeze one document version and recheck the grantor's rights."""

from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from access.permissions import permissions_in
from documents.models import DocumentVersion
from documents.views import file_response

from .models import ScoreDocument
from .scores import visible_documents, voice


def candidates(org, arrangements, voices):
    rows = ScoreDocument.objects.filter(
        organization=org,
        arrangement_id__in=arrangements,
        arrangement__active=True,
        document__organization=org,
        document__deleted_at=None,
        document__department=None,
        document__folder__department=None,
    ).select_related("document__folder", "part")
    return [
        row
        for row in rows
        if row.part_id is None or voice(row.part.instrument, row.part.register) in voices
    ]


def context(access):
    if hasattr(access, "assignment_id"):
        row = access.assignment
        return (
            row.organization,
            {p.arrangement_id for p in row.performance.program_entries.all() if p.arrangement_id},
            {voice(row.position.instrument, row.position.register)},
            row.status != "declined" and not row.performance.event.is_cancelled,
        )
    from .practice import occurrence
    from .practice_programs import program_for, with_programs

    row = access.invitation
    rehearsal = with_programs(type(row.rehearsal).objects.filter(pk=row.rehearsal_id)).get()
    o = occurrence(rehearsal.event, access.original_start)
    response = row.responses.filter(original_start=access.original_start).first()
    return (
        row.organization,
        {item["arrangement"] for item in program_for(rehearsal, access.original_start)["items"]},
        {voice(s.instrument, s.register) for s in row.musician.skills.all()},
        bool(o and not o.is_cancelled and (not response or response.status != "declined")),
    )


def choices(view, access):
    if (
        not {"docs.view", "docs.edit", "docs.manage"} <= view.org_permissions
        or "docs" not in view.org.enabled_modules
    ):
        return []
    org, arrangements, voices, enabled = context(access)
    if not enabled:
        return []
    available = set(visible_documents(view).values_list("pk", flat=True))
    selected = {share["score"] for share in access.score_shares}
    return [
        {"id": row.pk, "title": row.document.title, "selected": row.pk in selected}
        for row in candidates(org, arrangements, voices)
        if row.document_id in available and row.document.versions.exists()
    ]


def save(view, access, requested):
    if not {"docs.edit", "docs.view", "docs.manage"} <= view.org_permissions:
        raise PermissionDenied()
    ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), max_length=200
    ).run_validation(requested)
    available = {row["id"] for row in choices(view, access)}
    if not set(ids) <= available:
        raise PermissionDenied()
    shares = []
    for row in ScoreDocument.objects.filter(organization=view.org, pk__in=set(ids)).select_related(
        "document"
    ):
        version = row.document.versions.order_by("-uploaded_at", "-pk").first()
        shares.append(
            {
                "score": row.pk,
                "document": row.document_id,
                "version": version.pk,
                "folder": row.document.folder_id,
                "grantor": view.request.user.pk,
            }
        )
    access.score_shares = shares
    access.save(update_fields=["score_shares"])


def available(access):
    org, arrangements, voices, enabled = context(access)
    if not enabled or "docs" not in org.enabled_modules:
        return []
    allowed = {row.pk: row for row in candidates(org, arrangements, voices)}
    output = []
    for share in access.score_shares:
        row = allowed.get(share["score"])
        user = get_user_model().objects.filter(pk=share["grantor"], is_active=True).first()
        if (
            not row
            or not user
            or row.document_id != share["document"]
            or row.document.folder_id != share["folder"]
        ):
            continue
        perms = permissions_in(user, org)
        if not {"music.edit", "docs.view", "docs.edit", "docs.manage"} <= perms:
            continue
        # Only the owning organisation's document managers can issue grants.
        from documents.services import org_viewer

        if not org_viewer(org, perms).folders().filter(pk=row.document.folder_id).exists():
            continue
        version = DocumentVersion.objects.filter(pk=share["version"], document=row.document).first()
        if version:
            output.append((row, version))
    return output


def descriptions(access):
    return [
        {
            "id": row.pk,
            "title": row.document.title,
            "filename": version.name,
            "usage_note": row.usage_note,
        }
        for row, version in available(access)
    ]


def download(request, access, score_id):
    rows = {row.pk: version for row, version in available(access)}
    version = rows.get(score_id)
    if version is None:
        from rest_framework.exceptions import NotFound

        raise NotFound()
    return file_response(request, version)
