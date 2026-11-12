"""Gesamtaudit 11.11.2026, Fachfrage 1: Zwei-Faktor-Pflicht für jedes Verwaltungsrecht.

Frist 3 Tage; in der Frist ruhen Rundschreiben, Exporte und Buchen in der Kasse sofort.
"""

import datetime

import pytest
from django.utils import timezone

from access.catalog import (
    CIRCULARS_EDIT,
    CIRCULARS_VIEW,
    EXPORT_FULL,
    FINANCE_EDIT,
    FINANCE_VIEW,
    MEMBERS_EDIT,
)
from access.permissions import permissions_in
from accounts.mfa_policy import GRACE_DAYS, IMMEDIATE_PERMISSIONS
from accounts.models import User

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture(autouse=True)
def _sofort(settings):
    settings.MFA_IMMEDIATE = True


def _totp(user):
    from allauth.mfa.models import Authenticator

    Authenticator.objects.create(user=user, type=Authenticator.Type.TOTP, data={})
    return User.objects.get(pk=user.pk)


def test_frist_drei_tage_und_folgenreiche_rechte_ruhen_sofort(orgs, api, settings):
    settings.MFA_GRACE_DAYS = GRACE_DAYS
    club = orgs["a"]
    board = make_user("neu-vorstand@example.org")
    give_role(board, club)
    perms = permissions_in(board, club)
    board.refresh_from_db()
    assert GRACE_DAYS == 3
    assert board.mfa_required_by - timezone.now() <= datetime.timedelta(days=3)
    # in der Frist: lesen und Mitglieder bearbeiten ja, Rundschreiben, Export, Buchen nein
    assert {FINANCE_VIEW, CIRCULARS_VIEW, MEMBERS_EDIT} <= perms
    assert not perms & IMMEDIATE_PERMISSIONS
    assert {CIRCULARS_EDIT, EXPORT_FULL, FINANCE_EDIT} & perms == set()
    created = api(board).post(
        f"/api/orgs/{club.pk}/circulars/",
        {"subject": "Betrug", "body": "Bitte überweisen", "channel": "email"},
        content_type=JSON,
    )
    assert created.status_code == 403, created.content

    # mit zweitem Faktor wieder alles
    fresh = _totp(board)
    assert {CIRCULARS_EDIT, EXPORT_FULL, FINANCE_EDIT} <= permissions_in(fresh, club)


def test_nach_der_frist_ruhen_alle_rechte(orgs):
    club = orgs["a"]
    helper = make_user("helfer@example.org")
    give_role(helper, club, ["events.edit", "docs.view"], name="Termine")
    assert permissions_in(helper, club)
    User.objects.filter(pk=helper.pk).update(
        mfa_required_by=timezone.now() - datetime.timedelta(minutes=1)
    )
    helper.refresh_from_db()
    assert permissions_in(helper, club) == set()
    assert permissions_in(_totp(helper), club)


def test_abteilungsrechte_ebenso(orgs):
    from accounts.mfa_policy import gate

    user = make_user("zug@example.org")
    perms = {"dept.members.view", "dept.circulars.send"}
    in_frist = gate(user, set(perms))
    assert in_frist == {"dept.members.view"}
    User.objects.filter(pk=user.pk).update(
        mfa_required_by=timezone.now() - datetime.timedelta(minutes=1)
    )
    user.refresh_from_db()
    assert gate(user, set(perms)) == set()
