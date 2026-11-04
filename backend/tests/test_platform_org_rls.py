"""Plattformänderungen bei hinterlegter Kontaktrolle mit echtem PostgreSQL-RLS."""

import pytest
from django.db import connection

from access.catalog import PLATFORM_MANAGE, SWITCHABLE_MODULES
from access.models import Role
from audit.models import AuditEntry
from core.tenancy import get_rls
from organizations.models import Organization

from .factories import give_role, make_user
from .test_rls import as_app_role

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL-RLS erforderlich"),
]
JSON = "application/json"


@pytest.fixture(params=["superuser", "platform_role"])
def platform_admin(request):
    user = make_user("plattform@example.org", is_superuser=request.param == "superuser")
    if request.param == "platform_role":
        give_role(user, Organization.platform(), [PLATFORM_MANAGE], name="Plattformverwaltung")
    return user


def contact_role(org, source=Organization.ContactSource.ROLE):
    role = Role.objects.create(organization=org, name="Kontakt", permissions=["members.view"])
    org.contact_source = source
    org.contact_role = role
    org.save(update_fields=["contact_source", "contact_role"])
    return role


@pytest.mark.parametrize("org_key", ["a", "c", "federation"])
def test_platform_module_cycle_with_contact_role(orgs, platform_admin, api, org_key):
    org = orgs[org_key]
    role = contact_role(org)
    other = orgs["b"]
    other_modules = list(other.enabled_modules)
    client = api(platform_admin)
    url = f"/api/platform/orgs/{org.pk}/"
    for modules in [list(SWITCHABLE_MODULES), [], ["members", "music"]]:
        # Auch die übrigen Schalter aus dem Bearbeitungsformular mitsenden.
        with as_app_role():
            response = client.patch(
                url,
                {
                    "enabled_modules": modules,
                    "is_active": True,
                    "keeps_members": org.type == Organization.Type.CLUB,
                },
                content_type=JSON,
            )
            assert response.status_code == 200, response.content
            assert response.json()["enabled_modules"] == sorted(modules)
            # Keine Daten einer Einheit nach dem Request sichtbar lassen.
            assert not get_rls().bypass
            assert get_rls().org_id is None
            assert not Role.objects.exists()
        org.refresh_from_db()
        other.refresh_from_db()
        role.refresh_from_db()
        assert org.enabled_modules == sorted(modules)
        assert org.contact_role_id == role.pk
        assert org.contact_source == Organization.ContactSource.ROLE
        assert role.permissions == ["members.view"]
        assert other.enabled_modules == other_modules
    assert (
        AuditEntry.objects.filter(
            organization=org, user=platform_admin, action="update", object_id=str(org.pk)
        ).count()
        == 3
    )


def test_platform_update_scopes_validation_without_bypass(orgs, platform_admin, api, monkeypatch):
    org = orgs["a"]
    # Auch die gespeicherte Rolle bei derzeit eigenen Kontaktdaten wird validiert.
    contact_role(org, Organization.ContactSource.OWN)
    contact_role(orgs["b"])
    observed = []
    clean = Organization.clean

    def scoped_clean(instance):
        observed.append(
            (get_rls().bypass, set(Role.objects.values_list("organization_id", flat=True)))
        )
        return clean(instance)

    monkeypatch.setattr(Organization, "clean", scoped_clean)
    client = api(platform_admin)
    with as_app_role():
        response = client.patch(
            f"/api/platform/orgs/{org.pk}/", {"name": "Verein A 1900"}, content_type=JSON
        )
        assert response.status_code == 200, response.content
    assert observed == [(False, {org.pk})]
    org.refresh_from_db()
    assert org.name == "Verein A 1900"


def test_invalid_module_with_contact_role_leaves_settings_unchanged(orgs, platform_admin, api):
    org = orgs["a"]
    role = contact_role(org)
    before = list(org.enabled_modules)
    client = api(platform_admin)
    with as_app_role():
        response = client.patch(
            f"/api/platform/orgs/{org.pk}/", {"enabled_modules": ["unknown"]}, content_type=JSON
        )
        assert response.status_code == 400
        assert "enabled_modules" in response.json()
        assert get_rls().org_id is None
        assert not get_rls().bypass
        assert not Role.objects.exists()
    org.refresh_from_db()
    assert org.enabled_modules == before
    assert org.contact_role_id == role.pk


def test_club_board_cannot_change_platform_modules(orgs, board_a, api):
    org = orgs["a"]
    contact_role(org)
    before = list(org.enabled_modules)
    client = api(board_a)
    with as_app_role():
        response = client.patch(
            f"/api/platform/orgs/{org.pk}/", {"enabled_modules": []}, content_type=JSON
        )
        assert response.status_code == 403
        assert get_rls().org_id is None
    org.refresh_from_db()
    assert org.enabled_modules == before
