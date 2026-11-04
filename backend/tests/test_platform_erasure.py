import pytest
from django.core.files.base import ContentFile

from access.models import RoleAssignment
from audit.models import AuditEntry
from core.tenancy import tenant_context
from finance.models import Account, Booking
from members.models import Membership, Person
from organizations.models import Organization

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture
def admin(django_user_model):
    return django_user_model.objects.create_superuser(email="erase@example.org", password="x")


def erase(api, admin, org, confirmation=None):
    return api(admin).post(
        f"/api/platform/orgs/{org.pk}/erase/",
        {"confirmation": org.name if confirmation is None else confirmation},
        content_type=JSON,
    )


def test_erases_members_finance_roles_but_keeps_other_units_and_users(api, admin, orgs):
    org = orgs["c"]
    holder = make_user("holder@example.org")
    with tenant_context(org.pk):
        give_role(holder, org)
        person = Person.objects.create(
            scope=org, first_name="A", last_name="B", birth_date="1990-01-01"
        )
        Membership.objects.create(organization=org, scope=org, person=person)
        account = Account.objects.create(organization=org, name="Bank", opening_date="2026-01-01")
        booking = Booking.objects.create(
            organization=org,
            account=account,
            year=2026,
            number=1,
            date="2026-11-04",
            kind="income",
            amount="10.00",
            text="Test",
        )
    pk = org.pk
    response = erase(api, admin, org)
    assert response.status_code == 204, response.content
    assert not Organization.objects.filter(pk=pk).exists()
    assert not Membership.objects.filter(organization_id=pk).exists()
    assert not Person.objects.filter(pk=person.pk).exists()
    assert not Booking.objects.filter(pk=booking.pk).exists()
    assert not RoleAssignment.objects.filter(organization_id=pk).exists()
    assert holder.__class__.objects.filter(pk=holder.pk).exists()
    assert Organization.objects.filter(pk=orgs["a"].pk).exists()
    assert AuditEntry.objects.filter(
        organization=Organization.platform(), action="delete", object_id=str(pk)
    ).exists()


def test_requires_platform_permission(api, board_c, orgs):
    assert erase(api, board_c, orgs["c"]).status_code == 403
    assert Organization.objects.filter(pk=orgs["c"].pk).exists()


def test_requires_exact_name(api, admin, orgs):
    assert erase(api, admin, orgs["c"], "wrong").status_code == 400
    assert Organization.objects.filter(pk=orgs["c"].pk).exists()


def test_children_block_deletion(api, admin, orgs):
    assert erase(api, admin, orgs["federation"]).status_code == 400
    assert Organization.objects.filter(pk=orgs["a"].pk).exists()


def test_platform_cannot_be_deleted(api, admin):
    assert erase(api, admin, Organization.platform()).status_code == 404


def test_external_protected_reference_aborts_everything(api, admin, orgs):
    with tenant_context(orgs["c"].pk):
        account = Account.objects.create(
            organization=orgs["c"], name="Bank", opening_date="2026-01-01"
        )
    with tenant_context(orgs["a"].pk):
        booking = Booking.objects.create(
            organization=orgs["a"],
            account=account,
            year=2026,
            number=1,
            date="2026-11-04",
            kind="income",
            amount="10.00",
            text="Test",
        )
    assert erase(api, admin, orgs["c"]).status_code == 400
    assert Organization.objects.filter(pk=orgs["c"].pk).exists()
    assert Account.objects.filter(pk=account.pk).exists()
    with tenant_context(orgs["a"].pk):
        assert Booking.objects.filter(pk=booking.pk).exists()


def test_files_removed_after_commit(api, admin, orgs, django_capture_on_commit_callbacks):
    org = orgs["c"]
    org.logo.save("test.png", ContentFile(b"test"))
    storage, name = org.logo.storage, org.logo.name
    assert storage.exists(name)
    with django_capture_on_commit_callbacks(execute=True):
        assert erase(api, admin, org).status_code == 204
        assert storage.exists(name)
    assert not storage.exists(name)
