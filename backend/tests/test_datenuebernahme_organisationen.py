"""Datenübernahme mit Organisationsmitgliedern, Ansprechpartnern und Rechnungsanschrift (J6)."""

import pytest

from core.tenancy import rls_bypass
from members.models import BillingAddress, ContactPerson, Membership, Person
from organizations.models import Organization

from .test_datatransfer import (  # noqa: F401
    _eager,
    _on_commit_now,
    as_doc,
    export,
    platform_admin,  # noqa: F401
    upload,
)
from .test_m2_members import admit, make_types
from .test_organisationsmitglieder import admit_org

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture
def org_club(api, orgs, board_c):
    club = orgs["c"]
    types = make_types(club)
    c = api(board_c)
    person = admit(c, club, types["aktiv"]).json()
    firma = admit_org(c, club, types["foerder"]).json()
    base = f"/api/orgs/{club.pk}/members/{firma['id']}"
    assert (
        c.post(
            f"{base}/contacts/",
            {
                "last_name": "Muster",
                "first_name": "Max",
                "email": "max@musterbau.example",
                "function": "Geschäftsführer",
            },
            content_type=JSON,
        ).status_code
        == 201
    )
    assert (
        c.post(
            f"{base}/contacts/",
            {"member": person["id"], "function": "Prokuristin", "receives_invoices": False},
            content_type=JSON,
        ).status_code
        == 201
    )
    resp = c.put(
        f"{base}/billing-address/",
        {
            "name": "Musterbau GmbH Buchhaltung",
            "street": "Postfach 1",
            "postal_code": "12345",
            "city": "Musterstadt",
            "leitweg_id": "991-12345-67",
        },
        content_type=JSON,
    )
    assert resp.status_code == 200, resp.json()
    return {"club": club, "firma": firma, "person": person}


def test_organisation_mit_ansprechpartnern_kommt_mit(api, org_club, board_c, platform_admin):  # noqa: F811
    content, _ = export(api(board_c), f"/api/orgs/{org_club['club'].pk}")
    doc = as_doc(content)
    # Mit Organisationen neue Fassung; ältere Installationen lehnen die Datei verständlich ab
    assert doc["version"] == 2
    kinds = sorted(p.get("kind", "person") for p in doc["persons"])
    assert kinds == ["organization", "person"]
    c = api(platform_admin)
    job = upload(c, "/api/platform", content)
    assert not job["preview"]["error_count"], job["preview"]["errors"]
    c.post(f"/api/platform/datatransfer/imports/{job['id']}/run/")
    job = c.get(f"/api/platform/datatransfer/imports/{job['id']}/").json()
    assert job["status"] == "done", job
    club = Organization.objects.get(pk=job["result_organization"]["id"])
    with rls_bypass():
        firma = Person.objects.get(scope=club, kind="organization")
        assert firma.name_suffix == "Niederlassung Musterstadt"
        assert firma.legal_form == "gmbh" and firma.birth_date is None
        membership = Membership.objects.get(organization=club, person=firma)
        contacts = {c.function: c for c in ContactPerson.objects.filter(membership=membership)}
        assert set(contacts) == {"Geschäftsführer", "Prokuristin"}
        assert contacts["Geschäftsführer"].email == "max@musterbau.example"
        assert contacts["Geschäftsführer"].is_primary
        linked = contacts["Prokuristin"]
        # Verknüpfung zeigt auf die übernommene Person im neuen Verein
        assert linked.person.scope == club and linked.person.first_name == "Erika"
        assert not linked.receives_invoices
        billing = BillingAddress.objects.get(membership=membership)
        assert billing.leitweg_id == "991-12345-67" and billing.city == "Musterstadt"


def test_ohne_organisationen_bleibt_fassung_1(api, orgs, board_c):
    club = orgs["c"]
    admit(api(board_c), club, make_types(club)["aktiv"])
    content, _ = export(api(board_c), f"/api/orgs/{club.pk}")
    assert as_doc(content)["version"] == 1
