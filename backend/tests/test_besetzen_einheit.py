"""Rolle einer Untereinheit besetzen und den Vorgänger beenden (Rollen-Vorschlag R3)."""

from __future__ import annotations

import datetime

import pytest

from core.tenancy import tenant_context
from members.models import DepartmentRoleHolder
from organizations.models import Department, DepartmentRole

from .factories import make_member

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture
def zug(orgs):
    with tenant_context(orgs["a"].pk):
        return Department.objects.create(organization=orgs["a"], name="Jäger", founding_year=1950)


def test_akte_besetzt_und_beendet_vorgaenger(api, orgs, zug, board_a):
    a = orgs["a"]
    alt = make_member(a, "Anton", "Alt", departments=[zug])
    neu = make_member(a, "Nora", "Neu", departments=[zug])
    with tenant_context(a.pk):
        role = DepartmentRole.objects.create(department=zug, name="Zugführer")
        old = DepartmentRoleHolder.objects.create(
            organization=a, membership=alt, role=role, valid_from="2020-01-01"
        )
    resp = api(board_a).post(
        f"/api/orgs/{a.pk}/members/{neu.pk}/department-roles/",
        {"role": role.pk, "valid_from": "2026-03-15", "end_previous": True},
        content_type=JSON,
    )
    assert resp.status_code == 201, resp.content
    assert resp.json()["ended"] == ["Anton Alt"]
    old.refresh_from_db()
    assert old.valid_until == datetime.date(2026, 3, 14)


def test_akte_ohne_haekchen_bleibt_vorgaenger(api, orgs, zug, board_a):
    a = orgs["a"]
    alt = make_member(a, "Anton", "Alt", departments=[zug])
    neu = make_member(a, "Nora", "Neu", departments=[zug])
    with tenant_context(a.pk):
        role = DepartmentRole.objects.create(department=zug, name="Fahnenträger")
        old = DepartmentRoleHolder.objects.create(
            organization=a, membership=alt, role=role, valid_from="2020-01-01"
        )
    resp = api(board_a).post(
        f"/api/orgs/{a.pk}/members/{neu.pk}/department-roles/",
        {"role": role.pk, "valid_from": "2026-03-15"},
        content_type=JSON,
    )
    assert resp.status_code == 201
    assert resp.json()["ended"] == []
    old.refresh_from_db()
    assert old.valid_until is None
