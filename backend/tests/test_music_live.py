"""Live-Vorgabe: Leitung schickt das nächste Stück an alle Geräte derselben Mappe."""
# ruff: noqa: F811

import pytest
from django.core.cache import cache

from core.tenancy import tenant_context
from music.models import Musician, MusicLeader, Skill
from portal.models import PortalAccess

from .factories import give_role, make_member, make_user
from .test_music import JSON, c, club, music  # noqa: F401
from .test_music_score_folders import setup  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


def _second_musician(club):
    user = make_user("fluegelhorn@example.org")
    member = make_member(club, "Kim", "Beispiel")
    with tenant_context(club.pk):
        access = PortalAccess.objects.create(organization=club, membership=member, user=user)
        musician = Musician.objects.create(organization=club, membership=member)
        Skill.objects.create(organization=club, musician=musician, instrument="Flügelhorn")
    return user, access, musician


def test_leader_sends_and_others_receive(api, club, setup):
    book = setup["book"]
    leader = api(setup["user"])
    url = f"/api/portal/{setup['access'].pk}/music/live/folder-{book.pk}/"
    first = leader.get(url).json()
    assert first["cue"] is None and first["can_send"] is False
    assert leader.post(url, {"arrangement": setup["alte"].pk}, content_type=JSON).status_code == 403
    with tenant_context(club.pk):
        MusicLeader.objects.create(organization=club, musician=setup["musician"], folder=book)
    folders = leader.get(f"/api/portal/{setup['access'].pk}/music/folders/").json()["folders"]
    assert folders[0]["key"] == f"folder-{book.pk}" and folders[0]["can_lead"] is True
    sent = leader.post(url, {"arrangement": setup["alte"].pk, "number": "27"}, content_type=JSON)
    assert sent.status_code == 200, sent.content
    cue = sent.json()["cue"]
    assert cue["title"] == "Alte Kameraden" and cue["number"] == "27"
    # Gleich danach noch einmal: kurze Sperre gegen Doppeltippen
    assert leader.post(url, {"arrangement": setup["alte"].pk}, content_type=JSON).status_code == 400
    user, access, _ = _second_musician(club)
    other = api(user).get(f"/api/portal/{access.pk}/music/live/folder-{book.pk}/").json()
    assert other["cue"]["seq"] == cue["seq"] and other["can_send"] is False


def test_live_needs_visible_target(api, club, setup):
    client = api(setup["user"])
    base = f"/api/portal/{setup['access'].pk}/music/live/"
    assert client.get(base + "folder-999999/").status_code == 404
    assert client.get(base + "performance-999999/").status_code == 404
    assert client.get(base + "anders-1/").status_code == 404
    with tenant_context(club.pk):
        setup["book"].active = False
        setup["book"].save()
    assert client.get(base + f"folder-{setup['book'].pk}/").status_code == 404


def test_music_editor_may_send_and_manage_leaders(api, club, setup):
    give_role(setup["user"], club, permissions=["music.view", "music.edit"], name="Dirigent")
    client = api(setup["user"])
    url = f"/api/portal/{setup['access'].pk}/music/live/folder-{setup['book'].pk}/"
    assert client.get(url).json()["can_send"] is True
    base = f"/api/orgs/{club.pk}/music/leaders/"
    created = client.post(
        base, {"musician": setup["musician"].pk, "folder": setup["book"].pk}, content_type=JSON
    )
    assert created.status_code == 201, created.content
    assert client.get(base + f"?folder={setup['book'].pk}").json()[0]["name"]
    assert (
        client.post(
            base, {"musician": setup["musician"].pk, "folder": setup["book"].pk}, content_type=JSON
        ).status_code
        == 400
    )
    assert (
        client.post(base, {"musician": setup["musician"].pk}, content_type=JSON).status_code == 400
    )
    assert client.delete(base + f"{created.json()['id']}/").status_code == 204
