# ruff: noqa: F811  (Fixtures aus test_verbund_kopplung)
"""Organisationsmitglieder in der namentlichen Meldung (Verbund, Konzept J6; erfundene Daten)."""

import datetime

import pytest

from core.tenancy import tenant_context
from members import services as member_services
from members.models import Membership, MemberType, PersonKind
from peering import services
from peering.models import RemoteMember

from .factories import make_member
from .test_verbund_kopplung import VERBAND, VEREIN, _setup, api, couple, net, world  # noqa: F401
from .test_verbund_register import named, sync

pytestmark = pytest.mark.django_db
JSON = "application/json"


def admit_org(club, name="Musterbau GmbH", suffix="Niederlassung Musterstadt"):
    with tenant_context(club.pk):
        member_type, _ = MemberType.objects.get_or_create(
            organization=club, name="aktiv", defaults={"active": True}
        )
        return member_services.admit(
            club,
            {
                "kind": PersonKind.ORGANIZATION,
                "member_type": member_type,
                "entry_date": datetime.date(2020, 1, 1),
                "last_name": name,
                "name_suffix": suffix,
                "first_name": "",
                "birth_date": None,
                "email": "info@musterbau.example",
                "street": "Musterstraße 1",
                "postal_code": "12345",
                "city": "Musterstadt",
                "departments": [],
            },
        )


def register(upper):
    with tenant_context(upper.remote_unit.pk):
        return {
            m.person.display_name: m.person
            for m in Membership.objects.filter(organization=upper.remote_unit).select_related(
                "person"
            )
        }


@pytest.fixture
def firma(net, world):
    with net.on(VEREIN):
        make_member(world["club"], "Anna", "Aktiv")
        return admit_org(world["club"])


def test_organisation_wird_gemeldet(net, world, firma):
    lower, upper = named(net, world)
    reg = register(upper)
    org = reg["Musterbau GmbH – Niederlassung Musterstadt"]
    assert org.kind == PersonKind.ORGANIZATION
    assert org.birth_date is None and org.first_name == ""
    assert org.scope_id == world["fed"].pk
    # Verbandsnummer kommt beim Verein an
    rm = RemoteMember.objects.get(coupling=lower, uid=f"m{firma.pk}")
    assert rm.number
    # Namensänderung kommt als Berichtigung an
    person = firma.person
    person.name_suffix = "Zentrale"
    person.save()
    sync(net, lower)
    assert "Musterbau GmbH – Zentrale" in register(upper)


def test_gegenstelle_zu_alt_bekommt_keine_organisationen(net, world, firma):
    lower, upper = couple(net, world)
    peer = lower.peer
    peer.versions = [1]
    peer.save()
    from .verbund_netz import release

    with net.on(VEREIN):
        release(lower, {"unit": "on", "events": "on", "members": "b"})
    upper.refresh_from_db()
    assert sorted(register(upper)) == ["Anna Aktiv"]
    with net.on(VEREIN):
        data = (
            api(world["club_board"])
            .get(f"/api/orgs/{world['club'].pk}/peering/couplings/{lower.pk}/")
            .json()
        )
    assert data["organizations_withheld"] == 1
    # Nach dem Update der Gegenstelle merkt der tägliche Abgleich das und schickt nach
    with net.on(VEREIN):
        services.reconcile(lower)
        lower.refresh_from_db()
        assert 2 in lower.peer.versions
        services.sync(lower)
    assert "Musterbau GmbH – Niederlassung Musterstadt" in register(upper)


def test_gleichnamige_organisation_wird_klaerfall(net, world, firma):
    from organizations.models import Organization  # noqa: F401

    from .factories import make_org

    with net.on(VERBAND):
        nachbar = make_org("Nachbarverein Musterstadt", parent=world["fed"])
        admit_org(nachbar)
    lower, upper = named(net, world)
    rm = RemoteMember.objects.get(coupling=upper, uid=f"m{firma.pk}")
    assert rm.status == "unclear"
    with net.on(VERBAND):
        c = api(world["fed_board"])
        base = f"/api/orgs/{world['fed'].pk}/peering/couplings/{upper.pk}"
        case = c.get(f"{base}/").json()["register"]["unclear"][0]
        assert case["kind"] == "organization"
        assert case["candidates"][0]["name"] == "Musterbau GmbH – Niederlassung Musterstadt"
        resp = c.post(f"{base}/members/{rm.pk}/resolve/", {"person": None}, content_type=JSON)
    assert resp.status_code == 200, resp.json()
    rm.refresh_from_db()
    assert rm.status == "active" and rm.membership.person.kind == PersonKind.ORGANIZATION
