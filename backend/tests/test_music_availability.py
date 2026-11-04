"""Abwesenheiten, lokale Belegungen, private Konflikthinweise und Ersatzplanung."""
# ruff: noqa: F811

import datetime
import uuid
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from rest_framework.exceptions import ValidationError

from core.tenancy import tenant_context
from datatransfer.tables import IdMap, dump_rows, load_tables
from events.models import Event, EventException, EventResponse
from music.availability import Availability, performance_interval
from music.models import (
    Assignment,
    Musician,
    MusicianAbsence,
    MusicianClaim,
    Performance,
    Position,
    Rehearsal,
    RehearsalInvitation,
    RehearsalResponse,
)
from music.views import AssignmentViewSet, MusicAssignmentSerializer
from portal.models import PortalAccess

from .factories import give_role, make_user
from .test_music import JSON, c, club, music  # noqa: F401
from .test_music_practice import practice  # noqa: F401
from .test_music_staffing import assign, endpoint, staffing  # noqa: F401
from .test_rls import as_app_role

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _database_dates(music):
    music[1].refresh_from_db()


def flags(club, performance, musician):
    with tenant_context(club.pk):
        return Availability(
            club, [musician], performance.event, *performance_interval(performance)
        ).reasons(musician)


def absence(club, musician, start, end):
    return MusicianAbsence.objects.create(
        organization=club, musician=musician, starts_at=start, ends_at=end
    )


def test_absence_boundary_and_meeting_time(club, staffing):
    _, performance, _, _, musicians = staffing
    start = performance.event.starts_at
    with tenant_context(club.pk):
        row = absence(club, musicians[0], start - datetime.timedelta(hours=2), start)
    assert flags(club, performance, musicians[0]) == []
    with tenant_context(club.pk):
        performance.meeting_at = start - datetime.timedelta(hours=1)
        performance.save()
    assert flags(club, performance, musicians[0]) == ["absence"]
    with tenant_context(club.pk):
        row.starts_at = performance.event.ends_at
        row.ends_at = row.starts_at + datetime.timedelta(hours=1)
        row.save()
    assert flags(club, performance, musicians[0]) == []


def test_absence_crud_and_atomic_batch(c, club, staffing):
    base, performance, tuba, _, musicians = staffing
    data = {
        "musician": musicians[1].pk,
        "starts_at": performance.event.starts_at.isoformat(),
        "ends_at": performance.event.ends_at.isoformat(),
    }
    url = base + "/absences/"
    key = str(uuid.uuid4())
    response = c.post(url, data, content_type=JSON, HTTP_IDEMPOTENCY_KEY=key)
    assert response.status_code == 201, response.content
    pk = response.json()["id"]
    assert c.post(url, data, content_type=JSON, HTTP_IDEMPOTENCY_KEY=key).json()["id"] == pk
    assert set(response.json()) == {"id", "musician", "starts_at", "ends_at"}
    assert (
        c.patch(f"{url}{pk}/", {"ends_at": data["starts_at"]}, content_type=JSON).status_code == 400
    )
    assert assign(c, staffing, [(musicians[0], tuba), (musicians[1], tuba)]).status_code == 400
    assert (
        c.post(
            base + "/assignments/",
            {"performance": performance.pk, "position": tuba.pk, "musician": musicians[1].pk},
            content_type=JSON,
        ).status_code
        == 400
    )
    plan = c.get(endpoint(staffing)).json()
    assert next(m for m in plan["candidates"] if m["id"] == musicians[1].pk)["availability"] == [
        "absence"
    ]
    with tenant_context(club.pk):
        assert not performance.assignments.exists()
    assert c.delete(f"{url}{pk}/").status_code == 204
    assert assign(c, staffing, [(musicians[0], tuba), (musicians[1], tuba)]).status_code == 200


def test_other_performances_and_calendar_responses_are_private(c, club, staffing):
    _, performance, tuba, _, musicians = staffing
    with tenant_context(club.pk):
        event = Event.objects.create(
            organization=club,
            title="Vertraulicher Kalendertitel",
            visibility="board",
            starts_at=performance.event.starts_at,
            ends_at=performance.event.ends_at,
        )
        other = Performance.objects.create(organization=club, event=event)
        position = Position.objects.create(organization=club, performance=other, instrument="Tuba")
        row = Assignment.objects.create(
            organization=club,
            performance=other,
            position=position,
            musician=musicians[0],
            status="pending",
        )
    assert flags(club, performance, musicians[0]) == ["busy"]
    assert "Vertraulicher" not in c.get(endpoint(staffing)).content.decode()
    with tenant_context(club.pk):
        row.status = "declined"
        row.save()
        response = EventResponse.objects.create(
            organization=club,
            event=event,
            membership=musicians[0].membership,
            status="yes",
            source="member",
        )
    assert flags(club, performance, musicians[0]) == ["busy"]
    with tenant_context(club.pk):
        event.is_cancelled = True
        event.save()
    assert flags(club, performance, musicians[0]) == []
    with tenant_context(club.pk):
        response.event = performance.event
        response.status = "no"
        response.save()
    assert flags(club, performance, musicians[0]) == ["declined"]
    assert assign(c, staffing, [(musicians[0], tuba)]).status_code == 400


def test_rehearsal_series_moved_cancelled_and_declined(club, staffing):
    _, performance, _, _, musicians = staffing
    start = performance.event.starts_at
    with tenant_context(club.pk):
        event = Event.objects.create(
            organization=club,
            title="Serienprobe",
            starts_at=start - datetime.timedelta(days=7),
            ends_at=performance.event.ends_at - datetime.timedelta(days=7),
            repeat="weekly",
        )
        rehearsal = Rehearsal.objects.create(organization=club, event=event)
        invite = RehearsalInvitation.objects.create(
            organization=club, rehearsal=rehearsal, musician=musicians[0]
        )
    assert flags(club, performance, musicians[0]) == ["busy"]
    with tenant_context(club.pk):
        reply = RehearsalResponse.objects.create(
            organization=club, invitation=invite, original_start=start, status="declined"
        )
    assert flags(club, performance, musicians[0]) == []
    with tenant_context(club.pk):
        reply.delete()
        exc = EventException.objects.create(
            organization=club,
            event=event,
            original_start=start,
            starts_at=start + datetime.timedelta(hours=4),
            ends_at=performance.event.ends_at + datetime.timedelta(hours=4),
        )
    assert flags(club, performance, musicians[0]) == []
    with tenant_context(club.pk):
        exc.starts_at = start
        exc.ends_at = performance.event.ends_at
        exc.is_cancelled = True
        exc.save()
    assert flags(club, performance, musicians[0]) == []


def test_all_day_dst_and_adjacent_slots(club, staffing):
    _, performance, _, _, musicians = staffing
    berlin = ZoneInfo("Europe/Berlin")
    with tenant_context(club.pk):
        day = datetime.datetime(2027, 10, 31, tzinfo=berlin)
        event = Event.objects.create(
            organization=club, title="Ganztag", starts_at=day, ends_at=day, all_day=True
        )
        EventResponse.objects.create(
            organization=club,
            event=event,
            membership=musicians[0].membership,
            status="yes",
            source="member",
        )
        performance.event.starts_at = day.replace(hour=23, minute=30)
        performance.event.ends_at = day + datetime.timedelta(days=1)
        performance.event.save()
    assert flags(club, performance, musicians[0]) == ["busy"]
    with tenant_context(club.pk):
        performance.event.starts_at = day + datetime.timedelta(days=1)
        performance.event.ends_at = performance.event.starts_at + datetime.timedelta(hours=1)
        performance.event.save()
    assert flags(club, performance, musicians[0]) == []


def test_self_absences_are_scoped_and_idempotent(api, c, club, staffing):
    base, performance, _, _, musicians = staffing
    user = make_user("abwesend@example.org")
    with tenant_context(club.pk):
        access = PortalAccess.objects.create(
            organization=club, membership=musicians[0].membership, user=user
        )
    client = api(user)
    url = f"/api/portal/{access.pk}/music/absences/"
    payload = {
        "action": "save",
        "starts_at": performance.event.starts_at.isoformat(),
        "ends_at": performance.event.ends_at.isoformat(),
        "musician": musicians[1].pk,
    }
    key = str(uuid.uuid4())
    response = client.post(url, payload, content_type=JSON, HTTP_IDEMPOTENCY_KEY=key)
    assert response.status_code == 200, response.content
    pk = response.json()["id"]
    assert response.json()["musician"] == musicians[0].pk
    assert client.post(url, payload, content_type=JSON, HTTP_IDEMPOTENCY_KEY=key).json()["id"] == pk
    with tenant_context(club.pk):
        foreign = absence(
            club, musicians[1], performance.event.starts_at, performance.event.ends_at
        )
    assert (
        client.post(
            url,
            {**payload, "id": foreign.pk},
            content_type=JSON,
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        ).status_code
        == 404
    )
    assert [r["id"] for r in client.get(url).json()["items"]] == [pk]
    key = str(uuid.uuid4())
    data = {"action": "delete", "id": pk}
    assert client.post(url, data, content_type=JSON, HTTP_IDEMPOTENCY_KEY=key).status_code == 200
    assert client.post(url, data, content_type=JSON, HTTP_IDEMPOTENCY_KEY=key).status_code == 200
    reader = make_user("musiklesen@example.org")
    give_role(reader, club, permissions=["music.view"])
    assert api(reader).get(base + "/absences/").status_code == 200
    assert api(reader).delete(f"{base}/absences/{foreign.pk}/").status_code == 403
    club.enabled_modules.remove("music")
    club.save()
    assert client.get(url).json()["enabled"] is False
    assert c.get(base + "/absences/").status_code == 404


def test_existing_assignment_warns_and_reply_checks_again(api, c, club, staffing):
    _, performance, tuba, _, musicians = staffing
    user = make_user("antwort@example.org")
    with tenant_context(club.pk):
        access = PortalAccess.objects.create(
            organization=club, membership=musicians[0].membership, user=user
        )
        row = Assignment.objects.create(
            organization=club,
            performance=performance,
            position=tuba,
            musician=musicians[0],
            status="accepted",
        )
        claim = MusicianClaim.objects.create(
            organization=club, assignment=row, status="approved", attended=True
        )
        absence(club, musicians[0], performance.event.starts_at, performance.event.ends_at)
    result = c.get(endpoint(staffing)).json()
    assert result["assignments"][0]["status"] == "accepted"
    assert result["assignments"][0]["availability"] == ["absence"]
    client = api(user)
    url = f"/api/portal/{access.pk}/music/"
    assert (
        client.post(url, {"id": row.pk, "status": "accepted"}, content_type=JSON).status_code == 400
    )
    assert (
        client.post(url, {"id": row.pk, "status": "declined"}, content_type=JSON).status_code == 200
    )
    with tenant_context(club.pk):
        claim.refresh_from_db()
        assert claim.status == "approved"


def test_rehearsal_acceptance_checks_absence(api, club, practice):
    user, access, musician, event, invite, _ = practice
    with tenant_context(club.pk):
        row = absence(club, musician, event.starts_at, event.ends_at)
    client = api(user)
    url = f"/api/portal/{access.pk}/music/practice/"
    assert client.get(url).json()["rehearsals"][0]["availability"] == ["absence"]
    data = {"id": invite.pk, "original_start": event.starts_at.isoformat(), "status": "accepted"}
    assert client.post(url, data, content_type=JSON).status_code == 400
    assert client.post(url, {**data, "status": "declined"}, content_type=JSON).status_code == 200
    with tenant_context(club.pk):
        row.delete()
    assert client.post(url, data, content_type=JSON).status_code == 200


def test_revalidate_after_new_absence_and_roundtrip(c, club, orgs, staffing):
    _, performance, tuba, _, musicians = staffing
    user = make_user("einteilenfrei@example.org")
    give_role(user, club)
    with tenant_context(club.pk):
        view = AssignmentViewSet()
        view.org = club
        view.org_permissions = {"music.edit", "events.view"}
        view.request = SimpleNamespace(user=user)
        serializer = MusicAssignmentSerializer(
            data={"performance": performance.pk, "position": tuba.pk, "musician": musicians[0].pk},
            context={"view": view},
        )
        assert serializer.is_valid(), serializer.errors
        absence(club, musicians[0], performance.event.starts_at, performance.event.ends_at)
        with pytest.raises(ValidationError):
            view.perform_create(serializer)
        tables = {"music.musicianabsence": dump_rows(MusicianAbsence, club, None)}
    with as_app_role(), tenant_context(orgs["b"].pk):
        assert not MusicianAbsence.objects.exists()
    with tenant_context(orgs["b"].pk):
        other = Musician.objects.create(organization=orgs["b"], name="Gast B")
        ids = IdMap()
        ids.set("music.musician", musicians[0].pk, other.pk)
        assert load_tables(tables, orgs["b"], ids, None) == 1
        assert MusicianAbsence.objects.get().musician_id == other.pk
