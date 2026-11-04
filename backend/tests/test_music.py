"""Musikmodul: Fachablauf, Modulgrenze, Kalenderfreigaben und Mandanten."""
# ruff: noqa: F811

import pytest

from core.tenancy import tenant_context
from events.models import Event
from music.models import Assignment, Musician, Performance, Position, Skill
from portal.models import PortalAccess

from .factories import give_role, make_member, make_user
from .test_m9_billing import JSON, c, club  # noqa: F401
from .test_rls import as_app_role


def test_personal_response_is_limited_to_own_assignment(api, club, music):
    _, event = music
    member = make_member(club, "Alex", "Beispiel")
    user = make_user("musik@example.org")
    with tenant_context(club.pk):
        access = PortalAccess.objects.create(organization=club, membership=member, user=user)
        musician = Musician.objects.create(organization=club, membership=member)
        other = Musician.objects.create(organization=club, name="Anderer Gast")
        performance = Performance.objects.create(organization=club, event=event)
        position = Position.objects.create(
            organization=club, performance=performance, instrument="Tuba"
        )
        own = Assignment.objects.create(
            organization=club, performance=performance, position=position, musician=musician
        )
        foreign = Assignment.objects.create(
            organization=club, performance=performance, position=position, musician=other
        )
    client = api(user)
    url = f"/api/portal/{access.pk}/music/"
    assert [r["id"] for r in client.get(url).json()] == [own.pk]
    assert (
        client.post(url, {"id": foreign.pk, "status": "accepted"}, content_type=JSON).status_code
        == 404
    )
    assert (
        client.post(url, {"id": own.pk, "status": "accepted"}, content_type=JSON).status_code == 200
    )


def test_calendar_right_and_read_only(api, club, music):
    base, _ = music
    user = make_user("musik@example.org")
    give_role(user, club, permissions=["music.view"], name="Musik lesen")
    client = api(user)
    assert client.get(f"{base}/performances/").json() == []
    assert client.post(f"{base}/musicians/", {"name": "Gast"}, content_type=JSON).status_code == 403


def test_music_rls(club, orgs, music):
    with tenant_context(club.pk):
        row = Musician.objects.create(organization=club, name="Gast A")
    with as_app_role(), tenant_context(orgs["b"].pk):
        assert not Musician.objects.filter(pk=row.pk).exists()


pytestmark = pytest.mark.django_db


@pytest.fixture
def music(club):
    club.enabled_modules += ["music", "events"]
    club.save()
    with tenant_context(club.pk):
        event = Event.objects.create(
            organization=club,
            title="Musterkonzert",
            starts_at="2026-12-01T18:00:00Z",
            ends_at="2026-12-01T20:00:00Z",
        )
    return f"/api/orgs/{club.pk}/music", event


def test_performance_workflow(c, club, music):
    base, event = music

    def post(kind, data):
        r = c.post(f"{base}/{kind}/", data, content_type=JSON)
        assert r.status_code == 201, r.content
        return r.json()["id"]

    musician = post("musicians", {"name": "Alex Beispiel"})
    post("skills", {"musician": musician, "instrument": "Trompete", "primary": True})
    performance = post("performances", {"event": event.pk, "uniform": "Vereinsuniform"})
    position = post(
        "positions", {"performance": performance, "instrument": "Trompete", "required": 2}
    )
    assignment = post(
        "assignments", {"performance": performance, "position": position, "musician": musician}
    )
    r = c.patch(f"{base}/assignments/{assignment}/", {"status": "accepted"}, content_type=JSON)
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"
    assert c.get(f"{base}/performances/").json()[0]["title"] == "Musterkonzert"


def test_module_off(c, club, music):
    base, _ = music
    club.enabled_modules.remove("music")
    club.save()
    assert c.get(f"{base}/musicians/").status_code == 404


def test_reject_foreign_references(c, club, orgs, music):
    base, _ = music
    other = orgs["b"]
    with tenant_context(other.pk):
        guest = Musician.objects.create(organization=other, name="Fremder Gast")
    r = c.post(f"{base}/skills/", {"musician": guest.pk, "instrument": "Tuba"}, content_type=JSON)
    assert r.status_code == 400


def test_reject_unskilled_and_mismatched_position(c, club, music):
    base, event = music
    with tenant_context(club.pk):
        guest = Musician.objects.create(organization=club, name="Gast Beispiel")
        performance = Performance.objects.create(organization=club, event=event)
        position = Position.objects.create(
            organization=club, performance=performance, instrument="Tuba"
        )
    payload = {"performance": performance.pk, "position": position.pk, "musician": guest.pk}
    assert c.post(f"{base}/assignments/", payload, content_type=JSON).status_code == 400
    with tenant_context(club.pk):
        Skill.objects.create(organization=club, musician=guest, instrument="Tuba")
    assert c.post(f"{base}/assignments/", payload, content_type=JSON).status_code == 201
    assert c.post(f"{base}/assignments/", payload, content_type=JSON).status_code == 400


def test_series_not_a_performance(c, club, music):
    base, event = music
    with tenant_context(club.pk):
        event.repeat = "weekly"
        event.save()
    assert (
        c.post(f"{base}/performances/", {"event": event.pk}, content_type=JSON).status_code == 400
    )
