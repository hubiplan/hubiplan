"""Mitgliederbereich und App lesen die eingeschalteten Module (Modulverzeichnis, M7).

Erfundene Daten."""

import pytest

from portal.models import PortalAccess

from .factories import make_member, make_user

pytestmark = pytest.mark.django_db


def test_zugang_nennt_module(orgs, api):
    club = orgs["a"]
    club.enabled_modules = ["members", "portal", "events", "helpers"]
    club.member_portal_enabled = True
    club.save()
    membership = make_member(club, "Erika", "Beispiel", email="erika@example.org")
    user = make_user("erika@example.org")
    PortalAccess.objects.create(organization=club, membership=membership, user=user)
    data = api(user).get("/api/me/contexts/").json()
    access = data["portal"][0]
    assert access["modules"] == ["events", "helpers", "members", "portal"]
    # Die einzelnen Schalter bleiben für ältere App-Stände
    assert access["helpers_enabled"] is True and access["todos_enabled"] is False
