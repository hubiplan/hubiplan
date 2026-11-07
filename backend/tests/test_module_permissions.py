"""Modulfreigaben begrenzen Anzeige und Zugriff, ohne gespeicherte Rechte zu löschen."""

import datetime

import pytest

from access.catalog import (
    AREAS,
    NEW_TO_LEGACY,
    SWITCHABLE_MODULES,
    catalog_for,
    effective_for,
)
from access.models import Role
from access.permissions import permissions_in
from members.models import DepartmentRoleHolder
from organizations.models import Department, DepartmentRole, Organization
from portal.models import PortalAccess
from portal.services import department_contexts

from .factories import give_role, make_member, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


def enable(org, modules):
    org.enabled_modules = modules
    org.save(update_fields=["enabled_modules"])


# Module ohne eigenen Rechtebereich (z. B. Würden) bindet access/module_gate.py
WITH_AREAS = [m for m in SWITCHABLE_MODULES if any(a.module == m for a in AREAS)]


@pytest.mark.parametrize("module", WITH_AREAS)
def test_each_module_hides_all_areas_and_restores_rights(orgs, module):
    org = orgs["a"]
    user = make_user("module@example.org")
    role = give_role(user, org).role
    stored = list(role.permissions)
    areas = {a.id for a in AREAS if a.module == module}
    assert areas
    enable(org, list(SWITCHABLE_MODULES))
    assert areas <= {a["id"] for a in catalog_for("club", org)}
    enabled = permissions_in(user, org)
    enable(org, [m for m in SWITCHABLE_MODULES if m != module])
    assert not areas & {a["id"] for a in catalog_for("club", org)}
    # Frühere Codes eines anderen Bereichs bleiben (entries.manage gehört zu calls.edit)
    others = {
        old
        for new, olds in NEW_TO_LEGACY.items()
        if new.rpartition(".")[0] not in areas
        for old in olds
    }
    left = {c for c in permissions_in(user, org) if c.rpartition(".")[0] in areas}
    assert not left - others
    role.refresh_from_db()
    assert role.permissions == stored
    enable(org, list(SWITCHABLE_MODULES))
    assert permissions_in(user, org) == enabled


def test_members_extra_and_legacy_codes_are_blocked(orgs):
    org = orgs["a"]
    enable(org, [])
    codes = ["photos.manage", "cards.manage", "export.run", "events.manage", "website.manage"]
    assert effective_for(codes, org) == set()
    assert effective_for(["dept.members.edit", "dept.export"], org, dept=True) == set()
    catalog = catalog_for("club", org)
    assert "export.lists" not in {p["code"] for a in catalog for p in a["permissions"]}
    assert "logins" not in {a["id"] for a in catalog}
    assert {"roles", "settings"} <= {a["id"] for a in catalog}


def test_api_cycle_preserves_hidden_rights_on_edit(orgs, board_a, api):
    org = orgs["a"]
    client = api(board_a)
    enable(org, ["members", "music", "events"])
    role = Role.objects.create(
        organization=org, name="Musikleitung", permissions=["music.edit", "events.manage"]
    )
    music_user = make_user("music@example.org")
    assignment = give_role(music_user, org, role.permissions, name="Musikrolle")
    catalog_url = f"/api/permissions/?org_type=club&org={org.pk}"
    assert "music" in {a["id"] for a in client.get(catalog_url).json()}
    assert api(music_user).get(f"/api/orgs/{org.pk}/events/").status_code == 200
    enable(org, ["members"])
    assert "music" not in {a["id"] for a in client.get(catalog_url).json()}
    denied = api(music_user).get(f"/api/orgs/{org.pk}/events/")
    assert denied.status_code == 404
    assert api(music_user).get(f"/api/orgs/{org.pk}/music/musicians/").status_code == 404
    updated = client.patch(
        f"/api/orgs/{org.pk}/roles/{role.pk}/",
        {"permissions": ["members.view", "finance.edit"]},
        content_type=JSON,
    )
    assert updated.status_code == 200, updated.content
    role.refresh_from_db()
    assert set(role.permissions) == {
        "members.view",
        "music.view",
        "music.edit",
        "events.view",
        "events.edit",
    }
    enable(org, ["members", "music", "events"])
    assert "music" in {a["id"] for a in client.get(catalog_url).json()}
    assert {"music.edit", "events.manage"} <= permissions_in(music_user, org)
    assignment.role.refresh_from_db()
    assert "music.edit" in assignment.role.permissions


def test_disabled_rights_cannot_be_added_to_new_role(orgs, board_a, api):
    org = orgs["a"]
    enable(org, ["members"])
    response = api(board_a).post(
        f"/api/orgs/{org.pk}/roles/",
        {"name": "Neu", "permissions": ["music.edit", "events.manage", "members.view"]},
        content_type=JSON,
    )
    assert response.status_code == 201, response.content
    assert response.json()["permissions"] == ["members.view"]


def test_foreign_catalog_does_not_fall_back_to_unfiltered(orgs, board_a, api):
    assert (
        api(board_a).get(f"/api/permissions/?org_type=club&org={orgs['b'].pk}").status_code == 404
    )


def test_department_catalog_access_and_both_edit_paths(orgs, board_a, api):
    org = orgs["a"]
    org.department_access_enabled = True
    org.save()
    dept = Department.objects.create(organization=org, name="Gruppe", self_managed=True)
    member = make_member(org, "Maria", "Muster", departments=[dept])
    user = make_user("department@example.org")
    PortalAccess.objects.create(organization=org, membership=member, user=user)
    role = DepartmentRole.objects.create(
        organization=org,
        department=dept,
        name="Leitung",
        permissions=["roles.edit", "members.view", "events.edit", "export.lists"],
    )
    DepartmentRoleHolder.objects.create(
        organization=org,
        membership=member,
        role=role,
        valid_from=datetime.date(2020, 1, 1),
    )
    enable(org, [])
    ctx = department_contexts(user)[dept.pk]
    assert "roles.edit" in ctx.permissions
    assert (
        not {"events.edit", "dept.events.manage", "members.view", "dept.export"} & ctx.permissions
    )
    url = f"/api/depts/{dept.pk}/roles/"
    response = api(user).get(url)
    assert response.status_code == 200, response.content
    assert "events" not in {a["id"] for a in response.json()["catalog"]}
    for client, path in (
        (api(user), f"{url}{role.pk}/"),
        (api(board_a), f"/api/orgs/{org.pk}/department-roles/{role.pk}/"),
    ):
        response = client.patch(path, {"permissions": ["roles.edit"]}, content_type=JSON)
        assert response.status_code == 200, response.content
        role.refresh_from_db()
        assert {"events.edit", "members.view", "export.lists"} <= set(role.permissions)
    enable(org, ["members", "events"])
    assert {"dept.events.manage", "dept.export"} <= department_contexts(user)[dept.pk].permissions


def test_unit_workspace_cannot_bypass_parent_module_revocation(orgs):
    org = orgs["a"]
    unit = Department.objects.create(organization=org, name="Arbeitsbereich", own_workspace=True)
    user = make_user("unit@example.org")
    give_role(user, org, ["finance.edit", "roles.edit"])
    give_role(user, unit, ["finance.edit"])
    enable(org, ["finance"])
    assert "finance.edit" in permissions_in(user, unit)
    enable(org, [])
    unit.refresh_from_db()
    assert "finance.view" not in permissions_in(user, unit)
    assert "finance" not in {a["id"] for a in catalog_for("unit", unit)}


def test_superuser_and_preview_do_not_restore_disabled_module(orgs, api):
    org = orgs["a"]
    user = make_user("admin@example.org", is_superuser=True)
    give_role(user, org)
    role = Role.objects.create(organization=org, name="Ansicht", permissions=["music.edit"])
    enable(org, [])
    assert "music.edit" not in permissions_in(user, org)
    assert "platform.manage" in permissions_in(user, Organization.platform())
    client = api(user)
    response = client.post(f"/api/orgs/{org.pk}/ansicht/", {"role": role.pk}, content_type=JSON)
    assert response.status_code == 200
    summary = next(o for o in client.get("/api/me/organizations/").json() if o["id"] == org.pk)
    assert summary["permissions"] == []


def test_filter_does_not_expand_legacy_aliases_twice(orgs):
    org = orgs["a"]
    enable(org, ["website"])
    user = make_user("website@example.org")
    give_role(user, org, ["website.edit"])
    perms = permissions_in(user, org)
    assert "website.manage" in perms
    assert "webcontent.edit" not in perms
    assert "website.content" not in perms
