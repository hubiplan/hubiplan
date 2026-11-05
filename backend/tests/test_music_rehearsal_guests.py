"""Occurrence isolation and explicit, revocable version-level score grants."""
# ruff: noqa: F811

import uuid

import pytest
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import Client

from core.tenancy import tenant_context
from documents.models import Document, DocumentVersion, Folder
from music.models import RehearsalGuestAccess, RehearsalResponse, ScoreDocument

from .test_music import JSON, c, club, music  # noqa: F401
from .test_music_practice import practice  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def rehearsal_guest(club, practice):
    _, _, musician, event, invite, part = practice
    with tenant_context(club.pk):
        musician.membership = None
        musician.name = "Muster Gast"
        musician.save()
    return invite, event, part


def manage(c, club, invite, event, action="create", **values):
    return c.post(
        f"/api/orgs/{club.pk}/music/rehearsal-invitations/{invite.pk}/guest-access/",
        {"action": action, "original_start": event.starts_at.isoformat(), **values},
        content_type=JSON,
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )


def public(token, status=None, score=None):
    cache.clear()
    client = Client()
    url = "/api/music/guest-rehearsal/" + (f"?score={score}" if score else "")
    if status:
        return client.post(
            url,
            {"status": status, "original_start": "1999-01-01T00:00:00Z"},
            content_type=JSON,
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
    return client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")


def test_occurrence_response_rotation_and_email_revocation(c, club, rehearsal_guest):
    invite, event, _ = rehearsal_guest
    response = manage(c, club, invite, event)
    assert response.status_code == 200, response.content
    token = response.json()["url"].split("#probe-")[1]
    assert public(token).json()["title"] == "Musterprobe"
    assert public(token, "accepted").status_code == 200
    with tenant_context(club.pk):
        row = RehearsalResponse.objects.get(invitation=invite)
        assert row.original_start == event.starts_at  # request cannot choose another occurrence
    rotated = manage(c, club, invite, event, "rotate").json()["url"].split("#probe-")[1]
    assert public(token).status_code == 404
    assert public(rotated).status_code == 200
    assert (
        c.patch(
            f"/api/orgs/{club.pk}/music/musicians/{invite.musician_id}/",
            {"guest_email": "new-guest@example.org"},
            content_type=JSON,
        ).status_code
        == 200
    )
    assert public(rotated).status_code == 404


def test_explicit_score_grant_disappears_after_decline_or_program_change(c, club, rehearsal_guest):
    invite, event, part = rehearsal_guest
    club.enabled_modules = list(set([*club.enabled_modules, "docs"]))
    club.save()
    with tenant_context(club.pk):
        folder = Folder.objects.create(organization=club, name="Noten", public_key=Folder.new_key())
        document = Document.objects.create(organization=club, folder=folder, title="Tubastimme")
        DocumentVersion.objects.create(
            organization=club,
            document=document,
            name="tuba.pdf",
            content_type="application/pdf",
            file=ContentFile(b"%PDF-Muster", name="tuba.pdf"),
        )
        score = ScoreDocument.objects.create(
            organization=club, arrangement=part.arrangement, part=part, document=document
        )
    response = manage(c, club, invite, event)
    token = response.json()["url"].split("#probe-")[1]
    assert public(token).json()["scores"] == []
    assert public(token, score=score.pk).status_code == 404
    response = manage(c, club, invite, event, "share", scores=[score.pk])
    assert response.status_code == 200, response.content
    assert public(token).json()["scores"][0]["id"] == score.pk
    assert public(token, score=score.pk).status_code == 200
    assert public(token, "declined").status_code == 200
    assert public(token, score=score.pk).status_code == 404
    assert public(token, "accepted").status_code == 200
    with tenant_context(club.pk):
        invite.rehearsal.items.all().delete()
        assert RehearsalGuestAccess.objects.get(invitation=invite).score_shares
    assert public(token, score=score.pk).status_code == 404
