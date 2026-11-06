"""Rolle besetzen und den Vorgänger in einem Schritt beenden (Rollen-Vorschlag R2)."""

import datetime

import pytest

from access.models import RoleAssignment

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db


def url(org):
    return f"/api/orgs/{org.pk}/assignments/"


def test_besetzen_beendet_vorgaenger_zum_vortag(api, orgs, board_a):
    a = orgs["a"]
    old = give_role(make_user("alt@example.org"), a, ["finance.edit"], name="Kassierer")
    response = api(board_a).post(
        url(a),
        {
            "email": "neu@example.org",
            "role": old.role_id,
            "valid_from": "2026-03-15",
            "end_previous": True,
        },
        format="json",
    )
    assert response.status_code == 201, response.json()
    assert response.json()["ended"] == ["alt@example.org"]
    old.refresh_from_db()
    assert old.valid_until == datetime.date(2026, 3, 14)
    assert RoleAssignment.objects.filter(role=old.role, valid_until__isnull=True).count() == 1


def test_ohne_haekchen_bleibt_vorgaenger(api, orgs, board_a):
    a = orgs["a"]
    old = give_role(make_user("alt2@example.org"), a, ["finance.edit"], name="Kassierer")
    response = api(board_a).post(
        url(a),
        {"email": "zweite@example.org", "role": old.role_id, "valid_from": "2026-03-15"},
        format="json",
    )
    assert response.status_code == 201
    assert response.json()["ended"] == []
    old.refresh_from_db()
    assert old.valid_until is None


def test_eigene_rollenverwaltung_bleibt(api, orgs, board_a):
    """Wer sich selbst als Vorgänger beenden würde, verliert die Rollenverwaltung nicht."""
    a = orgs["a"]
    own = RoleAssignment.objects.get(organization=a, user=board_a)
    response = api(board_a).post(
        url(a),
        {
            "email": "nachfolge@example.org",
            "role": own.role_id,
            "valid_from": datetime.date.today().isoformat(),
            "end_previous": True,
        },
        format="json",
    )
    assert response.status_code == 400
    own.refresh_from_db()
    assert own.valid_until is None
