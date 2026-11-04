"""Performance notices: tenant boundaries, neutral content, retries and changes."""
# ruff: noqa: F811

import datetime
from types import SimpleNamespace

import pytest
from django.utils import timezone

from core.tenancy import tenant_context
from music.models import Assignment, Musician, Performance, PerformanceNotice, Position
from music.performance_tasks import assignment_notice, performance_reminders
from portal.models import PortalAccess

from .factories import make_member, make_user
from .test_music import JSON, c, club, music  # noqa: F401
from .test_rls import as_app_role

pytestmark = pytest.mark.django_db


@pytest.fixture
def notices(club, music, monkeypatch):
    _, event = music
    clock = SimpleNamespace(now=timezone.now().replace(microsecond=0))
    monkeypatch.setattr("music.performance_tasks.timezone.now", lambda: clock.now)
    user = make_user("auftritt@example.org")
    member = make_member(club, "Alex", "Beispiel")
    with tenant_context(club.pk):
        event.starts_at = clock.now + datetime.timedelta(days=10)
        event.ends_at = event.starts_at + datetime.timedelta(hours=2)
        event.save()
        access = PortalAccess.objects.create(organization=club, membership=member, user=user)
        musician = Musician.objects.create(organization=club, membership=member)
        performance = Performance.objects.create(organization=club, event=event)
        position = Position.objects.create(
            organization=club, performance=performance, instrument="Tuba"
        )
        assignment = Assignment.objects.create(
            organization=club, performance=performance, musician=musician, position=position
        )
    sent = []
    monkeypatch.setattr(
        "music.performance_tasks.mail.send",
        lambda *args, **kwargs: sent.append((args, kwargs)) or True,
    )
    return SimpleNamespace(
        clock=clock,
        user=user,
        access=access,
        musician=musician,
        performance=performance,
        event=event,
        assignment=assignment,
        sent=sent,
        org=club,
    )


def test_invitation_is_neutral_and_deduplicated(notices):
    n = notices
    assert assignment_notice.run(n.assignment.pk) == 1
    assert assignment_notice.run(n.assignment.pk) == 0
    assert n.sent[0][0][0] == n.user.email
    assert n.sent[0][0][1] == "Neue Auftrittseinteilung im Mitgliederbereich"
    assert "Musterkonzert" not in n.sent[0][0][2]
    assert "mein-bereich" in n.sent[0][0][2]
    assert n.sent[0][1]["organization"].pk == n.org.pk


def test_changes_cancel_and_restore_each_notify_once(notices):
    n = notices
    assert assignment_notice.run(n.assignment.pk) == 1
    for field, value in [
        ("location", "Anderer Treffpunkt"),
        ("is_cancelled", True),
        ("is_cancelled", False),
    ]:
        n.clock.now += datetime.timedelta(minutes=6)
        with tenant_context(n.org.pk):
            setattr(n.event, field, value)
            n.event.save()
        assert performance_reminders.run() == 1
        assert performance_reminders.run() == 0
    assert n.sent[-2][0][1] == "Auftritt abgesagt"
    assert n.sent[-1][0][1] == "Auftrittsinformationen geändert"
    assert all("Anderer Treffpunkt" not in args[2] for args, _ in n.sent)


def test_reminder_only_pending_once_and_not_directly_after_invitation(notices):
    n = notices
    with tenant_context(n.org.pk):
        n.event.starts_at = n.clock.now + datetime.timedelta(days=2)
        n.event.ends_at = n.event.starts_at + datetime.timedelta(hours=2)
        n.event.save()
    assert assignment_notice.run(n.assignment.pk) == 1
    n.clock.now += datetime.timedelta(minutes=6)
    assert performance_reminders.run() == 0
    n.clock.now += datetime.timedelta(days=1)
    assert performance_reminders.run() == 1
    assert performance_reminders.run() == 0
    assert n.sent[-1][0][1] == "Erinnerung an eine Auftrittsrückmeldung"


def test_explicit_request_after_acceptance_not_lost_to_throttle(notices):
    n = notices
    assert assignment_notice.run(n.assignment.pk) == 1
    with tenant_context(n.org.pk):
        n.assignment.status = "accepted"
        n.assignment.save()
    assert assignment_notice.run(n.assignment.pk) == 0
    with tenant_context(n.org.pk):
        n.assignment.status = "pending"
        n.assignment.save()
    n.clock.now += datetime.timedelta(minutes=6)
    assert assignment_notice.run(n.assignment.pk) == 1
    assert n.sent[-1][0][1] == "Neue Auftrittseinteilung im Mitgliederbereich"


def test_failed_delivery_retries_without_claiming_success(notices, monkeypatch):
    n = notices
    monkeypatch.setattr("music.performance_tasks.mail.send", lambda *a, **kw: False)
    assert assignment_notice.run(n.assignment.pk) == 0
    with tenant_context(n.org.pk):
        state = PerformanceNotice.objects.get(assignment=n.assignment)
        assert state.fingerprint == "" and state.notified_at is None
    monkeypatch.setattr("music.performance_tasks.mail.send", lambda *a, **kw: True)
    assert assignment_notice.run(n.assignment.pk) == 0
    n.clock.now += datetime.timedelta(minutes=6)
    assert assignment_notice.run(n.assignment.pk) == 1
    assert assignment_notice.run(n.assignment.pk) == 0


@pytest.mark.parametrize(
    "condition",
    [
        "disabled",
        "inactive",
        "inactive_user",
        "former",
        "guest",
        "declined",
        "cancelled",
        "past",
        "no_access",
        "no_portal",
    ],
)
def test_ineligible_assignments_do_not_send(notices, condition):
    n = notices
    with tenant_context(n.org.pk):
        if condition == "disabled":
            n.org.enabled_modules.remove("music")
            n.org.save()
        elif condition == "inactive":
            n.musician.active = False
            n.musician.save()
        elif condition == "inactive_user":
            n.user.is_active = False
            n.user.save()
        elif condition == "former":
            n.musician.membership.periods.update(
                exit_date=n.clock.now.date() - datetime.timedelta(days=1)
            )
        elif condition == "guest":
            n.musician.membership = None
            n.musician.save()
        elif condition == "declined":
            n.assignment.status = "declined"
            n.assignment.save()
        elif condition == "cancelled":
            n.event.is_cancelled = True
            n.event.save()
        elif condition == "past":
            n.event.starts_at = n.clock.now - datetime.timedelta(hours=2)
            n.event.ends_at = n.clock.now - datetime.timedelta(hours=1)
            n.event.save()
        elif condition == "no_access":
            n.access.delete()
        else:
            n.org.member_portal_enabled = False
            n.org.save()
    assert assignment_notice.run(n.assignment.pk) == 0
    assert not n.sent


def test_existing_assignments_are_baselined_without_invitation(notices):
    n = notices
    with tenant_context(n.org.pk):
        PerformanceNotice.objects.create(
            organization=n.org,
            assignment=n.assignment,
            fingerprint="baseline",
            last_status="pending",
        )
    assert assignment_notice.run(n.assignment.pk) == 0
    n.clock.now += datetime.timedelta(days=8)
    assert performance_reminders.run() == 1


def test_notice_state_is_tenant_isolated(notices, orgs):
    n = notices
    assert assignment_notice.run(n.assignment.pk) == 1
    with as_app_role(), tenant_context(orgs["b"].pk):
        assert not PerformanceNotice.objects.filter(assignment_id=n.assignment.pk).exists()


def test_reminder_bounds_in_api(c, club, music):
    base, event = music
    assert (
        c.post(
            f"{base}/performances/", {"event": event.pk, "remind_days": 31}, content_type=JSON
        ).status_code
        == 400
    )
    assert (
        c.post(
            f"{base}/performances/", {"event": event.pk, "remind_days": 0}, content_type=JSON
        ).status_code
        == 201
    )
