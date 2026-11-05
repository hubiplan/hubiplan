"""Live readiness, bounded range, finance privacy and shared score accounting."""
# ruff: noqa: F811

import datetime

import pytest
from django.utils import timezone

from core.tenancy import tenant_context
from music.models import (
    Arrangement,
    Assignment,
    Musician,
    MusicianAbsence,
    Performance,
    PerformanceAccount,
    Piece,
    Position,
    ProgramEntry,
    ScoreLoan,
    ScorePart,
)

from .factories import give_role, make_user
from .test_m9_billing import c, club  # noqa: F401
from .test_music import music  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def ready(club, music):
    base, event = music
    with tenant_context(club.pk):
        person = Musician.objects.create(organization=club, name="Muster Gast")
        performance = Performance.objects.create(organization=club, event=event)
        position = Position.objects.create(
            organization=club, performance=performance, instrument="Tuba"
        )
        assignment = Assignment.objects.create(
            organization=club,
            performance=performance,
            position=position,
            musician=person,
            status="accepted",
        )
        piece = Piece.objects.create(organization=club, title="Musterstück")
        arrangement = Arrangement.objects.create(
            organization=club, piece=piece, name="Konzertfassung"
        )
        part = ScorePart.objects.create(
            organization=club, arrangement=arrangement, instrument="Tuba", copies=1
        )
        ProgramEntry.objects.create(
            organization=club, performance=performance, arrangement=arrangement
        )
    return base, event, performance, person, assignment, part


def overview(c, base):
    response = c.get(f"{base}/performances/overview/", {"start": "2026-11-01", "end": "2026-12-31"})
    assert response.status_code == 200, response.content
    return response.json()


def test_ready_then_pending_and_conflict_are_live(c, club, ready):
    base, event, performance, person, assignment, _ = ready
    row = overview(c, base)["results"][0]
    assert row["status"] == "ready" and row["accepted"] == 1 and row["issues"] == []
    with tenant_context(club.pk):
        assignment.status = "pending"
        assignment.save()
        MusicianAbsence.objects.create(
            organization=club, musician=person, starts_at=event.starts_at, ends_at=event.ends_at
        )
    row = overview(c, base)["results"][0]
    codes = {item["code"]: item["count"] for item in row["issues"]}
    assert (
        row["status"] == "critical"
        and codes["pending"] == codes["missing_players"] == codes["conflicts"] == 1
    )
    assert "Muster Gast" not in str(row)


def test_scores_held_by_performer_are_not_reported_missing(c, club, ready):
    base, _, _, person, _, part = ready
    with tenant_context(club.pk):
        ScoreLoan.objects.create(
            organization=club,
            part=part,
            musician=person,
            quantity=1,
            due_on=datetime.date(2026, 12, 2),
        )
    assert overview(c, base)["results"][0]["status"] == "ready"
    with tenant_context(club.pk):
        stranger = Musician.objects.create(organization=club, name="Nicht eingeteilt")
        ScoreLoan.objects.update(musician=stranger)
    issues = overview(c, base)["results"][0]["issues"]
    assert next(item for item in issues if item["code"] == "missing_scores")["count"] == 1


def test_unplanned_and_cancelled_do_not_look_ready(c, club, ready):
    base, event, performance, *_ = ready
    with tenant_context(club.pk):
        performance.program_entries.all().delete()
    row = overview(c, base)["results"][0]
    assert row["status"] == "attention" and row["issues"][0]["code"] == "program"
    with tenant_context(club.pk):
        event.is_cancelled = True
        event.save()
    row = overview(c, base)["results"][0]
    assert row["status"] == "cancelled" and row["issues"] == []


def test_finance_and_calendar_rights_do_not_leak(api, c, club, ready):
    base, event, performance, *_ = ready
    with tenant_context(club.pk):
        event.starts_at = timezone.make_aware(datetime.datetime(2026, 11, 2, 18))
        event.ends_at = timezone.make_aware(datetime.datetime(2026, 11, 2, 20))
        event.save()
        PerformanceAccount.objects.create(organization=club, performance=performance, fee=100)
    reader = make_user("overview-reader@example.org")
    give_role(reader, club, ["music.view", "events.view"], name="Auftrittsübersicht lesen")
    client = api(reader)
    row = overview(client, base)
    assert row["finance_visible"] is False
    assert not any(item["area"] == "settlement" for item in row["results"][0]["issues"])
    no_calendar = make_user("no-calendar@example.org")
    give_role(no_calendar, club, ["music.view"], name="Nur Musikübersicht")
    assert overview(api(no_calendar), base)["results"] == []


def test_range_pagination_and_module_boundary(c, club, ready):
    base, *_ = ready
    assert (
        c.get(
            f"{base}/performances/overview/", {"start": "2026-12-31", "end": "2026-11-01"}
        ).status_code
        == 400
    )
    assert (
        c.get(
            f"{base}/performances/overview/", {"start": "2025-01-01", "end": "2027-01-01"}
        ).status_code
        == 400
    )
    assert c.get(f"{base}/performances/overview/", {"start": "invalid"}).status_code == 400
    assert (
        c.get(
            f"{base}/performances/overview/", {"start": "9999-12-30", "end": "9999-12-31"}
        ).status_code
        == 400
    )
    club.enabled_modules.remove("music")
    club.save()
    assert c.get(f"{base}/performances/overview/").status_code == 404
