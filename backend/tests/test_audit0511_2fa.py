"""Gesamtaudit 05.11. F-02: Pflicht-2FA auch für das Lesen aller Mitglieder und des Postausgangs."""

import datetime

import pytest
from django.utils import timezone

from access.catalog import AUDIT_VIEW, MEMBERS_VIEW
from access.permissions import permissions_in
from accounts.models import User

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db


def _overdue(user):
    User.objects.filter(pk=user.pk).update(
        mfa_required_by=timezone.now() - datetime.timedelta(minutes=1)
    )
    user.refresh_from_db()


def test_mitglieder_und_postausgang_lesen_ruhen_ohne_zweiten_faktor(orgs, api):
    club = orgs["a"]
    reader = make_user("lesen@example.org")
    give_role(reader, club, ["members.view", "audit.view"], name="Lesen")
    c = api(reader)
    assert c.get(f"/api/orgs/{club.pk}/members/").status_code == 200
    reader.refresh_from_db()
    assert reader.mfa_required_by is not None  # Übergangsfrist beginnt

    _overdue(reader)
    perms = permissions_in(reader, club)
    assert MEMBERS_VIEW not in perms and AUDIT_VIEW not in perms
    c = api(reader)
    # Ohne übrige Rechte ist die Einheit gar nicht mehr sichtbar (404)
    assert c.get(f"/api/orgs/{club.pk}/members/").status_code in (403, 404)
    assert c.get(f"/api/orgs/{club.pk}/outbox/").status_code in (403, 404)


def test_ohne_heikle_rechte_keine_pflicht(orgs, api):
    club = orgs["a"]
    user = make_user("termine@example.org")
    give_role(user, club, ["events.view"], name="Termine")
    permissions_in(user, club)
    user.refresh_from_db()
    assert user.mfa_required_by is None
