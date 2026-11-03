"""Gesamtaudit 03.11.2026: Regressionstests zu GA-S01 und GA-S02 (erfundene Daten)."""
# ruff: noqa: F811  (Fixtures als Parameter)

import pytest

from members.models import ContactDetails, Membership

from .factories import found
from .test_m3_workflows import JSON, member, types, url  # noqa: F401
from .test_rls import as_app_role

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _liste(settings, tmp_path):
    settings.LOESCHLISTE_PATH = str(tmp_path / "loeschliste" / "loeschliste.jsonl")


def _auch_in_b(api, orgs, types, member, board_b):
    resp = api(board_b).post(
        f"/api/orgs/{orgs['b'].pk}/members/admit/",
        {
            "person": member["person_id"],
            **found(member["person_id"]),
            "member_type": types["b"]["passiv"].pk,
            "entry_date": "2020-01-01",
            "email": "e@example.org",
            "street": "x",
            "postal_code": "1",
            "city": "y",
        },
        content_type=JSON,
    )
    assert resp.status_code == 201, resp.json()


# --- GA-S01: Löschen auf Verlangen in A kürzt keine Person, die B noch braucht ---


def test_loeschen_in_a_laesst_person_fuer_b_unter_app_rolle(
    api, orgs, types, member, board_a, board_b, django_capture_on_commit_callbacks
):
    _auch_in_b(api, orgs, types, member, board_b)
    person = Membership.objects.get(organization=orgs["a"]).person
    geburtstag = (person.birth_date.month, person.birth_date.day)
    assert geburtstag != (1, 1)
    c = api(board_a)
    c.post(
        url(orgs, member, "exit/"),
        {"exit_date": "2024-06-30", "exit_reason": "exit"},
        content_type=JSON,
    )
    # Echte App-Rolle: Verein A sieht die Mitgliedschaft in B nicht
    with as_app_role(), django_capture_on_commit_callbacks(execute=True):
        resp = c.post(url(orgs, member, "erase/"))
    assert resp.status_code == 200, resp.json()
    assert Membership.objects.get(organization=orgs["a"]).purged_at is not None
    person.refresh_from_db()
    assert not person.birth_year_only
    assert (person.birth_date.month, person.birth_date.day) == geburtstag
    # Gemeinsame Kontaktdaten bleiben für B
    assert ContactDetails.objects.filter(person=person, organization__isnull=True).exists()
    b = Membership.objects.get(organization=orgs["b"])
    assert b.purged_at is None


def test_loeschen_ohne_weitere_mitgliedschaft_kuerzt_weiter(
    api, orgs, member, board_a, django_capture_on_commit_callbacks
):
    c = api(board_a)
    c.post(
        url(orgs, member, "exit/"),
        {"exit_date": "2024-06-30", "exit_reason": "exit"},
        content_type=JSON,
    )
    with as_app_role(), django_capture_on_commit_callbacks(execute=True):
        assert c.post(url(orgs, member, "erase/")).status_code == 200
    person = Membership.objects.get(organization=orgs["a"]).person
    person.refresh_from_db()
    assert person.birth_year_only
    assert not ContactDetails.objects.filter(person=person).exists()


# --- GA-S02: 2FA-Reset beachtet Ämter in Untereinheiten anderer Vereine ---


def _totp(user):
    from allauth.mfa.models import Authenticator

    return Authenticator.objects.create(user=user, type=Authenticator.Type.TOTP, data={})


@pytest.fixture
def zugfuehrer_in_b(orgs, api, board_b):
    """Konto mit Amt im Zug von Verein B (Rechte über den Mitgliederzugang)."""
    from members.models import DepartmentRoleHolder
    from organizations.models import Department, DepartmentRole
    from portal.models import PortalAccess

    from .factories import make_member

    club = orgs["b"]
    club.member_portal_enabled = True
    club.department_access_enabled = True
    club.save()
    zug = Department.objects.create(
        self_managed=True, organization=club, name="Jägerzug", founding_year=1950
    )
    role = DepartmentRole.objects.create(
        organization=club,
        department=zug,
        name="Zugführer",
        permissions=["dept.members.view", "dept.members.edit"],
    )
    m = make_member(club, "Karl", "Zug", "karl@example.org", departments=[zug])
    DepartmentRoleHolder.objects.create(
        organization=club, membership=m, role=role, valid_from="2020-01-01"
    )
    assert api(board_b).post(f"/api/orgs/{club.pk}/members/{m.pk}/access/").status_code == 200
    return PortalAccess.objects.get(membership=m).user


def test_reset_mfa_nicht_bei_amt_in_fremder_untereinheit(orgs, api, board_a, zugfuehrer_in_b):
    from allauth.mfa.models import Authenticator

    from accounts.models import User
    from portal.services import department_contexts

    from .factories import give_role

    ziel = zugfuehrer_in_b
    zuordnung = give_role(ziel, orgs["a"], name="Beisitz")
    _totp(ziel)
    _totp(board_a)
    assert any(ctx.permissions for ctx in department_contexts(ziel).values())
    board = User.objects.get(pk=board_a.pk)
    with as_app_role():
        resp = api(board).post(f"/api/orgs/{orgs['a'].pk}/assignments/{zuordnung.pk}/reset-mfa/")
    assert resp.status_code == 400, resp.json()
    assert "Plattform" in resp.json()["detail"]
    assert Authenticator.objects.filter(user=ziel).exists()


def test_reset_mfa_bei_amt_ohne_rechte_erlaubt(orgs, api, board_a, zugfuehrer_in_b):
    """Ein Amt ohne Rechte (reines Ehrenamt) blockiert den Reset nicht."""
    from allauth.mfa.models import Authenticator

    from accounts.models import User
    from organizations.models import DepartmentRole

    from .factories import give_role

    DepartmentRole.objects.update(permissions=[])
    ziel = zugfuehrer_in_b
    zuordnung = give_role(ziel, orgs["a"], name="Beisitz")
    _totp(ziel)
    _totp(board_a)
    board = User.objects.get(pk=board_a.pk)
    resp = api(board).post(f"/api/orgs/{orgs['a'].pk}/assignments/{zuordnung.pk}/reset-mfa/")
    assert resp.status_code == 200, resp.json()
    assert not Authenticator.objects.filter(user=ziel).exists()
