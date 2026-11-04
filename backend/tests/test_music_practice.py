"""Proben, persönliche Noten und rückverfolgbare Bestandsbewegungen."""
# ruff: noqa: F811

import datetime
import uuid

import pytest
from django.utils import timezone

from core.tenancy import tenant_context
from documents.models import Document, Folder
from events.models import Event, EventException
from music.models import (
    Arrangement,
    Musician,
    Piece,
    Rehearsal,
    RehearsalInvitation,
    RehearsalItem,
    ScoreDocument,
    ScoreLoan,
    ScorePart,
    Skill,
)
from music.practice_tasks import rehearsal_reminders
from portal.models import PortalAccess

from .factories import give_role, make_member, make_user
from .test_music import JSON, c, club, music  # noqa: F401
from .test_rls import as_app_role

pytestmark = pytest.mark.django_db


def test_stock_correction_rechecks_after_a_checkout(club, practice):
    from types import SimpleNamespace
    from rest_framework.exceptions import ValidationError
    from music.scores import MusicScorePartSerializer, ScorePartViewSet

    user, _, musician, _, _, part = practice
    with tenant_context(club.pk):
        view = ScorePartViewSet()
        view.org = club
        view.request = SimpleNamespace(user=user)
        serializer = MusicScorePartSerializer(
            part, data={"copies": 0}, partial=True, context={"view": view}
        )
        assert serializer.is_valid(), serializer.errors
        ScoreLoan.objects.create(
            organization=club, part=part, musician=musician, quantity=1, due_on=timezone.localdate()
        )
        with pytest.raises(ValidationError):
            view.perform_update(serializer)
        part.refresh_from_db()
        assert part.copies == 2


def test_preparation_counts_only_current_assignments(club, practice):
    from music.models import Assignment, Performance, Position, ProgramEntry
    from music.scores import program_data

    _, _, musician, event, _, part = practice
    with tenant_context(club.pk):
        performance = Performance.objects.create(organization=club, event=event)
        position = Position.objects.create(
            organization=club, performance=performance, instrument="Tuba", register="1"
        )
        Assignment.objects.create(
            organization=club,
            performance=performance,
            position=position,
            musician=musician,
            status="accepted",
        )
        ProgramEntry.objects.create(
            organization=club, performance=performance, arrangement=part.arrangement
        )
        ScoreLoan.objects.create(
            organization=club, part=part, musician=musician, quantity=2, due_on=timezone.localdate()
        )
        other_event = Event.objects.create(
            organization=club,
            title="Anderer Termin",
            starts_at=event.starts_at,
            ends_at=event.ends_at,
        )
        other = Performance.objects.create(organization=club, event=other_event)
        other_position = Position.objects.create(
            organization=club, performance=other, instrument="Tuba", register="1"
        )
        Assignment.objects.create(
            organization=club,
            performance=other,
            position=other_position,
            musician=musician,
            status="declined",
        )
        row = program_data(performance)["preparation"][0]["voices"][0]
        assert row["held"] == 2 and row["available"] == 0 and row["missing_copies"] == 0


@pytest.fixture
def practice(club, music):
    user = make_user("probe@example.org")
    member = make_member(club, "Mika", "Beispiel")
    start = (timezone.now() + datetime.timedelta(days=1)).replace(microsecond=0)
    with tenant_context(club.pk):
        access = PortalAccess.objects.create(organization=club, membership=member, user=user)
        musician = Musician.objects.create(organization=club, membership=member)
        Skill.objects.create(organization=club, musician=musician, instrument="Tuba", register="1")
        event = Event.objects.create(
            organization=club,
            title="Musterprobe",
            starts_at=start,
            ends_at=start + datetime.timedelta(hours=2),
            repeat="weekly",
        )
        rehearsal = Rehearsal.objects.create(
            organization=club, event=event, remind_days=2, focus="Rhythmus"
        )
        invite = RehearsalInvitation.objects.create(
            organization=club, rehearsal=rehearsal, musician=musician
        )
        piece = Piece.objects.create(organization=club, title="Musterlied")
        arr = Arrangement.objects.create(organization=club, piece=piece, name="Musterfassung")
        RehearsalItem.objects.create(
            organization=club, rehearsal=rehearsal, arrangement=arr, focus="Takte 1 bis 8"
        )
        part = ScorePart.objects.create(
            organization=club, arrangement=arr, instrument="Tuba", register="1", copies=2
        )
    return user, access, musician, event, invite, part


def post(c, url, data, key=None):
    return c.post(url, data, content_type=JSON, HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()))


def test_issue_partial_return_retry_and_stock(c, club, practice):
    _, _, musician, _, _, part = practice
    url = f"/api/orgs/{club.pk}/music/loans/"
    data = {
        "action": "issue",
        "part": part.pk,
        "musician": musician.pk,
        "quantity": 2,
        "due_on": (timezone.localdate() + datetime.timedelta(days=7)).isoformat(),
    }
    key = str(uuid.uuid4())
    response = post(c, url, data, key)
    assert response.status_code == 200, response.content
    loan = response.json()["id"]
    assert post(c, url, data, key).json()["id"] == loan
    assert post(c, url, data).status_code == 400
    stock_url = f"/api/orgs/{club.pk}/music/parts/{part.pk}/"
    assert c.patch(stock_url, {"copies": 1}, content_type=JSON).status_code == 400
    ret = {"action": "return", "loan": loan, "quantity": 1}
    key = str(uuid.uuid4())
    assert post(c, url, ret, key).json()["returned"] == 1
    assert post(c, url, ret, key).json()["returned"] == 1
    assert post(c, url, {**ret, "quantity": 2}).status_code == 400
    assert post(c, url, ret).json()["returned"] == 2
    assert c.patch(stock_url, {"copies": 1}, content_type=JSON).status_code == 200


def test_personal_occurrence_response_and_cancel(api, club, practice):
    user, access, _, event, invite, _ = practice
    client = api(user)
    url = f"/api/portal/{access.pk}/music/practice/"
    rows = client.get(url).json()["rehearsals"]
    assert len(rows) > 1
    assert rows[0]["items"][0]["focus"] == "Takte 1 bis 8"
    data = {"id": invite.pk, "original_start": rows[0]["original_start"], "status": "accepted"}
    assert post(client, url, data).status_code == 200
    rows = client.get(url).json()["rehearsals"]
    assert rows[0]["status"] == "accepted" and rows[1]["status"] == "pending"
    with tenant_context(club.pk):
        EventException.objects.create(
            organization=club, event=event, original_start=event.starts_at, is_cancelled=True
        )
    assert post(client, url, data).status_code == 400
    assert post(client, url, {**data, "id": invite.pk + 1000}).status_code == 404
    assert (
        post(
            client,
            url,
            {**data, "original_start": (event.starts_at + datetime.timedelta(hours=1)).isoformat()},
        ).status_code
        == 400
    )


def test_scores_need_voice_and_member_folder(api, club, practice):
    user, access, _, _, _, part = practice
    with tenant_context(club.pk):
        folder = Folder.objects.create(
            organization=club, name="Probenoten", visibility="board", public_key=Folder.new_key()
        )
        document = Document.objects.create(organization=club, folder=folder, title="Eigene Stimme")
        own = ScoreDocument.objects.create(
            organization=club, arrangement=part.arrangement, part=part, document=document
        )
        other = ScorePart.objects.create(
            organization=club, arrangement=part.arrangement, instrument="Flöte", copies=1
        )
        ScoreDocument.objects.create(
            organization=club, arrangement=part.arrangement, part=other, document=document
        )
    client = api(user)
    url = f"/api/portal/{access.pk}/music/practice/"
    assert client.get(url).json()["scores"] == []
    with tenant_context(club.pk):
        folder.visibility = "members"
        folder.save()
    assert [s["id"] for s in client.get(url).json()["scores"]] == [own.pk]
    with tenant_context(club.pk):
        folder.visibility = "board"
        folder.save()
    assert client.get(f"/api/portal/{access.pk}/music/files/{own.pk}/").status_code == 404


def test_reminders_deduplicate_and_skip_responses(monkeypatch, api, club, practice):
    user, access, _, _, invite, _ = practice
    sent = []
    monkeypatch.setattr(
        "music.practice_tasks.mail.send", lambda *args, **kwargs: sent.append(args) or True
    )
    assert rehearsal_reminders.run() == 1
    assert rehearsal_reminders.run() == 0
    assert len(sent) == 1
    assert "Musterprobe" not in sent[0][2]  # Mail enthält keine vertraulichen Termindetails.


def test_read_only_and_foreign_loan(api, c, club, orgs, practice):
    _, _, musician, _, _, part = practice
    user = make_user("musiklesen@example.org")
    give_role(user, club, permissions=["music.view"], name="Musikleser")
    assert (
        post(api(user), f"/api/orgs/{club.pk}/music/loans/", {"action": "issue"}).status_code == 403
    )
    with tenant_context(orgs["b"].pk):
        foreign = Musician.objects.create(organization=orgs["b"], name="Gast B")
    assert (
        post(
            c,
            f"/api/orgs/{club.pk}/music/loans/",
            {
                "action": "issue",
                "part": part.pk,
                "musician": foreign.pk,
                "quantity": 1,
                "due_on": timezone.localdate().isoformat(),
            },
        ).status_code
        == 404
    )
    with as_app_role(), tenant_context(orgs["b"].pk):
        assert not RehearsalInvitation.objects.filter(musician=musician).exists()
