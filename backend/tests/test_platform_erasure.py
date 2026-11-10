import datetime

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone

from access.models import RoleAssignment
from audit.models import AuditEntry
from core.tenancy import tenant_context
from finance.models import Account, Booking, YearClosing
from members import loeschliste
from members.models import Membership, Person
from organizations import deletion
from organizations.models import Department, Organization

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture
def admin(django_user_model):
    return django_user_model.objects.create_superuser(email="erase@example.org", password="x")


def erase(api, admin, org, confirmation=None, *, prepare=True, **extra):
    """Zweistufig: vormerken, Wartezeit und Fristen überspringen, endgültig löschen."""
    if prepare:
        mark(api, admin, org)
    data = {
        "confirmation": org.name if confirmation is None else confirmation,
        "confirmed_by": "Kassenprüfer Muster",
        **extra,
    }
    return api(admin).post(f"/api/platform/orgs/{org.pk}/erase/", data, content_type=JSON)


def mark(api, admin, org, days_ago=60):
    resp = api(admin).post(
        f"/api/platform/orgs/{org.pk}/erase-request/", {"confirmation": org.name}, content_type=JSON
    )
    if resp.status_code == 204:
        Organization.objects.filter(pk=org.pk).update(
            erase_requested_at=timezone.now() - datetime.timedelta(days=days_ago)
        )
    return resp


@pytest.fixture(autouse=True)
def later(monkeypatch):
    """Standard: alle Fristen abgelaufen (einzelne Tests setzen einen anderen Tag)."""
    monkeypatch.setattr(deletion, "_today", lambda: datetime.date(2040, 1, 1))


def _booking(org, date="2026-11-04"):
    with tenant_context(org.pk):
        account = Account.objects.create(organization=org, name="Bank", opening_date="2026-01-01")
        return Booking.objects.create(
            organization=org,
            account=account,
            year=2026,
            number=1,
            date=date,
            kind="income",
            amount="10.00",
            text="Test",
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
    assert erase(api, admin, orgs["federation"]).status_code == 400, "Vereine darunter"
    assert Organization.objects.filter(pk=orgs["a"].pk).exists()


def test_platform_cannot_be_deleted(api, admin):
    assert erase(api, admin, Organization.platform(), prepare=False).status_code == 404


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


def test_first_step_only_deactivates_and_keeps_data(api, admin, orgs, monkeypatch):
    monkeypatch.setattr(deletion, "_today", timezone.localdate)
    org = orgs["c"]
    booking = _booking(org)
    assert erase(api, admin, org, prepare=False).status_code == 400
    assert mark(api, admin, org, days_ago=0).status_code == 204
    org.refresh_from_db()
    assert not org.is_active
    assert org.erase_requested_at and org.erase_requested_by == admin
    with tenant_context(org.pk):
        assert Booking.objects.filter(pk=booking.pk).exists()
    # Zweite Stufe frühestens nach der Wartezeit (und nach den Fristen)
    resp = erase(api, admin, org, prepare=False)
    assert resp.status_code == 400
    assert "30 Tage" in str(resp.content, "utf-8")
    assert Organization.objects.filter(pk=org.pk).exists()


def test_retention_blocks_until_deadline(api, admin, orgs, monkeypatch):
    org = orgs["c"]
    _booking(org)
    mark(api, admin, org)
    state = api(admin).get(f"/api/platform/orgs/{org.pk}/erase-state/").json()
    # Buchung 2026: Bücher zehn Jahre bis Ende 2036
    assert state["retention_until"] == "2037-01-01"
    assert state["has_finance"]
    monkeypatch.setattr(deletion, "_today", lambda: datetime.date(2036, 12, 31))
    assert erase(api, admin, org, prepare=False).status_code == 400
    monkeypatch.setattr(deletion, "_today", lambda: datetime.date(2037, 1, 1))
    # Mit Finanzdaten: wer hat die Fristen bestätigt?
    assert erase(api, admin, org, prepare=False, confirmed_by="").status_code == 400
    assert erase(api, admin, org, prepare=False).status_code == 204
    assert not Organization.objects.filter(pk=org.pk).exists()


def test_retention_hold_blocks(api, admin, orgs):
    org = orgs["c"]
    _booking(org)
    with tenant_context(org.pk):
        YearClosing.objects.create(organization=org, year=2026, retention_hold="Prüfung")
    resp = erase(api, admin, org)
    assert resp.status_code == 400
    assert "Löschsperre" in str(resp.content, "utf-8")


def test_marked_unit_cannot_be_reactivated_until_withdrawn(api, admin, orgs):
    org = orgs["c"]
    mark(api, admin, org)
    url = f"/api/platform/orgs/{org.pk}/"
    assert api(admin).patch(url, {"is_active": True}, content_type=JSON).status_code == 400
    assert api(admin).post(f"{url}erase-withdraw/").status_code == 204
    org.refresh_from_db()
    assert org.erase_requested_at is None and not org.is_active
    assert api(admin).patch(url, {"is_active": True}, content_type=JSON).status_code == 200
    org.refresh_from_db()
    assert org.is_active


def test_units_below_are_deactivated_and_erased(api, admin, orgs):
    club = orgs["c"]
    with tenant_context(club.pk):
        zug = Department.objects.create(organization=club, name="Herolde")
        sub = Department.objects.create(organization=club, parent=zug, name="Gruppe")
    mark(api, admin, club)
    assert not Organization.objects.get(pk=sub.pk).is_active
    assert erase(api, admin, club, prepare=False).status_code == 204
    assert not Organization.objects.filter(pk__in=[club.pk, zug.pk, sub.pk]).exists()


def test_erased_unit_stays_erased_after_restore(
    api, admin, orgs, settings, tmp_path, django_capture_on_commit_callbacks
):
    settings.LOESCHLISTE_PATH = str(tmp_path / "loeschliste" / "loeschliste.jsonl")
    org = orgs["c"]
    pk, created, name = org.pk, org.created_at, org.name
    with django_capture_on_commit_callbacks(execute=True):
        assert erase(api, admin, org).status_code == 204
    assert [item["e"] for item in loeschliste.unit_entries()] == [pk]
    # „Älteres Backup“: dieselbe Einheit mit Kennung und Anlagezeit ist wieder da
    restored = Organization.objects.create(
        pk=pk, name=name, type="club", founding_year=1900, street="S", postal_code="1", city="C"
    )
    Organization.objects.filter(pk=pk).update(created_at=created)
    with tenant_context(pk):
        person = Person.objects.create(
            scope=restored, first_name="A", last_name="B", birth_date="1990-01-01"
        )
        Membership.objects.create(organization=restored, scope=restored, person=person)
    loeschliste.apply()
    assert not Organization.objects.filter(pk=pk).exists()
    assert not Membership.objects.filter(organization_id=pk).exists()


def test_other_unit_with_reused_number_is_not_touched(orgs, settings, tmp_path):
    settings.LOESCHLISTE_PATH = str(tmp_path / "loeschliste" / "loeschliste.jsonl")
    org = orgs["c"]
    loeschliste.note_unit(org.pk, org.created_at - datetime.timedelta(days=1))
    loeschliste.apply()
    assert Organization.objects.filter(pk=org.pk).exists()
