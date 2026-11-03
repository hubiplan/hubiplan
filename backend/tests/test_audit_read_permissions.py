"""Direkte Bereichsgrenzen und minimale Basisauskunft (S11/FQ19/V09)."""

import importlib
import uuid

import pytest
from django.apps import apps
from django.db import connection

from access.models import Role
from access.permissions import permissions_in
from organizations.models import Department, DepartmentRole

from .factories import give_role, make_member, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


def client_for(api, org, permissions):
    user = make_user(f"rolle-{uuid.uuid4().hex}@example.org")
    give_role(user, org, permissions, name=f"Prüfrolle {user.pk}")
    return api(user)


@pytest.mark.parametrize(
    "suffix,permission",
    [
        ("", "settings.view"),
        ("theme/", "theme.view"),
        ("imprint/", "settings.view"),
        ("letterhead/", "settings.view"),
        ("departments/", "settings.view"),
        ("department-roles/", "roles.view"),
    ],
)
def test_get_requires_own_area(orgs, api, suffix, permission):
    org = orgs["a"]
    path = f"/api/orgs/{org.pk}/{suffix}"
    assert client_for(api, org, ["finance.view"]).get(path).status_code == 403
    reader = client_for(api, org, [permission])
    assert reader.get(path).status_code == 200
    assert reader.patch(path, {}, content_type=JSON).status_code in (403, 405)
    assert reader.get(f"/api/orgs/{orgs['b'].pk}/{suffix}").status_code == 404


def test_choices_do_not_leak_settings_or_roles(orgs, api):
    org = orgs["a"]
    unit = Department.objects.create(organization=org, name="Testgruppe")
    DepartmentRole.objects.create(
        organization=org, department=unit, name="Verwaltung", permissions=["members.edit"]
    )
    c = client_for(api, org, ["members.view"])
    response = c.get(f"/api/orgs/{org.pk}/department-choices/")
    assert response.status_code == 200
    [row] = response.json()
    assert row["id"] == unit.pk
    assert row["roles"] == []
    assert (
        not {"fiscal_start_month", "fee_exempt", "effective_theme", "own_website", "member_count"}
        & row.keys()
    )
    assert c.post(
        f"/api/orgs/{org.pk}/department-choices/", {"name": "unzulässig"}, content_type=JSON
    ).status_code in (403, 405)
    assert Department.objects.filter(organization=org).count() == 1


def test_embedded_roles_respect_area(orgs, api):
    org = orgs["a"]
    unit = Department.objects.create(organization=org, name="Testgruppe")
    role = DepartmentRole.objects.create(organization=org, department=unit, name="Leitung")
    c = client_for(api, org, ["settings.view"])
    assert c.get(f"/api/orgs/{org.pk}/departments/").json()[0]["roles"] == []
    c = client_for(api, org, ["roles.view"])
    data = c.get(f"/api/orgs/{org.pk}/department-choices/").json()
    assert data[0]["roles"][0]["id"] == role.pk


def test_member_options_are_minimal_and_cannot_write(orgs, api):
    org = orgs["a"]
    c = client_for(api, org, ["members.view"])
    url = f"/api/orgs/{org.pk}/member-settings/"
    data = c.get(url).json()
    assert "jubilee_years" in data
    assert not {"contact_effective", "street", "imprint_key", "contact_email"} & data.keys()
    assert c.patch(url, {"photo_approval_required": False}, content_type=JSON).status_code == 403


def test_settings_does_not_grant_roles_or_assign_holders(orgs, api):
    org = orgs["a"]
    unit = Department.objects.create(organization=org, name="Testgruppe", own_workspace=True)
    user = make_user("einstellungen@example.org")
    give_role(user, org, ["settings.edit", "members.edit"], name="Nur Einstellungen")
    assert "roles.edit" not in permissions_in(user, unit)
    role = DepartmentRole.objects.create(
        organization=org, department=unit, name="Leitung", permissions=["members.edit"]
    )
    member = make_member(org, "Ada", "Beispiel")
    c = api(user)
    assert (
        c.post(
            f"/api/orgs/{org.pk}/department-roles/",
            {"department": unit.pk, "name": "Neu"},
            content_type=JSON,
        ).status_code
        == 403
    )
    assert (
        c.post(
            f"/api/orgs/{org.pk}/members/{member.pk}/department-roles/",
            {"role": role.pk, "valid_from": "2026-01-01"},
            content_type=JSON,
        ).status_code
        == 403
    )
    assert (
        c.post(
            f"/api/orgs/{org.pk}/departments/{unit.pk}/manager/",
            {"member": member.pk},
            content_type=JSON,
        ).status_code
        == 403
    )


def test_migration_preserves_only_existing_implicit_role_authority(orgs):
    org = orgs["a"]
    old = Role.objects.create(organization=org, name="Bestehend", permissions=["settings.edit"])
    migration = importlib.import_module("access.migrations.0017_rollenhoheit")
    with connection.schema_editor() as editor:
        migration.forwards(apps, editor)
    old.refresh_from_db()
    assert {"roles.view", "roles.edit"} <= set(old.permissions)
    new = Role.objects.create(organization=org, name="Neu", permissions=["settings.edit"])
    assert "roles.edit" not in new.permissions
