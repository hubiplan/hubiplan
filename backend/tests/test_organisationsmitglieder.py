"""Organisationen (Firma, Verein, Behörde …) als Mitglieder (Konzept juristische Personen, J1)."""

from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from billing.models import AgeRate, FeeRate
from billing.services import yearly_fee
from core.tenancy import tenant_context
from members import services
from members.models import Membership, Person

from .test_m2_members import admit, make_types

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture
def types(orgs):
    return {key: make_types(orgs[key]) for key in ("a", "b", "c")}


def admit_org(client, org, member_type, **extra):
    data = {
        "kind": "organization",
        "last_name": "Musterbau GmbH",
        "name_suffix": "Niederlassung Musterstadt",
        "legal_form": "gmbh",
        "register": "Amtsgericht Musterstadt HRB 12345",
        "vat_id": "DE123456789",
        "website": "https://musterbau.example",
        "email": "info@musterbau.example",
        "street": "Musterstraße 1",
        "postal_code": "12345",
        "city": "Musterstadt",
        "member_type": member_type.pk,
        "entry_date": "2020-01-01",
    }
    data.update(extra)
    return client.post(f"/api/orgs/{org.pk}/members/admit/", data, content_type=JSON)


class TestAufnahme:
    def test_organisation_ohne_vorname_und_geburtsdatum(self, api, orgs, types, board_a):
        resp = admit_org(api(board_a), orgs["a"], types["a"]["foerder"])
        assert resp.status_code == 201, resp.json()
        data = resp.json()
        assert data["kind"] == "organization"
        assert data["first_name"] == ""
        assert data["birth_date"] is None
        assert data["organization"]["legal_form"] == "gmbh"
        assert data["organization"]["legal_form_label"] == "GmbH"
        assert data["organization"]["name_suffix"] == "Niederlassung Musterstadt"
        person = Person.objects.get()
        assert person.is_organization
        assert person.birth_date is None
        assert person.marks_version == 1
        assert str(person) == "Musterbau GmbH"
        assert person.display_name == "Musterbau GmbH – Niederlassung Musterstadt"

    def test_personenangaben_werden_verworfen(self, api, orgs, types, board_a):
        resp = admit_org(
            api(board_a),
            orgs["a"],
            types["a"]["foerder"],
            first_name="Erika",
            birth_date="1980-05-17",
            gender="weiblich",
        )
        assert resp.status_code == 201, resp.json()
        person = Person.objects.get()
        assert (person.first_name, person.birth_date, person.gender) == ("", None, "")

    def test_name_ist_pflicht(self, api, orgs, types, board_a):
        resp = admit_org(api(board_a), orgs["a"], types["a"]["foerder"], last_name="")
        assert resp.status_code == 400
        assert not Person.objects.exists()

    def test_person_braucht_weiter_geburtsdatum(self, api, orgs, types, board_a):
        resp = admit(api(board_a), orgs["a"], types["a"]["aktiv"], birth_date="")
        assert resp.status_code == 400
        assert not Person.objects.exists()

    def test_datenbank_verlangt_geburtsdatum_bei_personen(self, orgs):
        with pytest.raises(IntegrityError), transaction.atomic():
            Person.objects.create(scope=orgs["federation"], last_name="Muster", first_name="Max")

    def test_organisationsangaben_bei_personen_verworfen(self, api, orgs, types, board_a):
        resp = admit(api(board_a), orgs["a"], types["a"]["aktiv"], legal_form="gmbh")
        assert resp.status_code == 201, resp.json()
        assert resp.json()["organization"] is None
        assert Person.objects.get().legal_form == ""


class TestDubletten:
    def test_gleicher_name_wird_gefunden(self, api, orgs, types, board_a):
        c = api(board_a)
        assert admit_org(c, orgs["a"], types["a"]["foerder"]).status_code == 201
        # Anderer Verein im selben Dachverband findet die Organisation
        with tenant_context(orgs["b"].pk):
            found = services.find_duplicates(
                orgs["b"], " musterbau gmbh ", "", None, organization=True
            )
        assert [p.last_name for p in found] == ["Musterbau GmbH"]
        resp = c.get(
            f"/api/orgs/{orgs['a'].pk}/members/duplicates/",
            {"typ": "organisation", "name": "Musterbau GmbH"},
        )
        assert resp.status_code == 200, resp.json()
        assert [(d["kind"], d["already_member_here"]) for d in resp.json()] == [
            ("organization", True)
        ]

    def test_person_mit_gleichem_namen_ist_keine_dublette(self, api, orgs, types, board_a):
        c = api(board_a)
        assert admit(c, orgs["a"], types["a"]["aktiv"], last_name="Musterbau GmbH").status_code
        with tenant_context(orgs["a"].pk):
            found = services.find_duplicates(
                orgs["a"], "Musterbau GmbH", "", None, organization=True
            )
        assert found == []

    def test_namensaenderung_erneuert_suchmarken(self, api, orgs, types, board_a):
        c = api(board_a)
        member = admit_org(c, orgs["a"], types["a"]["foerder"]).json()
        resp = c.patch(
            f"/api/orgs/{orgs['a'].pk}/members/{member['id']}/",
            {"last_name": "Musterbau AG", "legal_form": "ag"},
            content_type=JSON,
        )
        assert resp.status_code == 200, resp.json()
        with tenant_context(orgs["a"].pk):
            assert (
                services.find_duplicates(orgs["a"], "Musterbau GmbH", "", None, organization=True)
                == []
            )
            found = services.find_duplicates(orgs["a"], "Musterbau AG", "", None, organization=True)
        assert len(found) == 1
        assert found[0].marks_version == 1


class TestAkte:
    def test_aendern_ohne_personenfelder(self, api, orgs, types, board_a):
        c = api(board_a)
        member = admit_org(c, orgs["a"], types["a"]["foerder"]).json()
        resp = c.patch(
            f"/api/orgs/{orgs['a'].pk}/members/{member['id']}/",
            {"name_suffix": "", "birth_date": "1990-01-01", "first_name": "Max"},
            content_type=JSON,
        )
        assert resp.status_code == 200, resp.json()
        person = Person.objects.get()
        assert person.name_suffix == ""
        assert (person.first_name, person.birth_date) == ("", None)

    def test_name_darf_nicht_leer_werden(self, api, orgs, types, board_a):
        c = api(board_a)
        member = admit_org(c, orgs["a"], types["a"]["foerder"]).json()
        resp = c.patch(
            f"/api/orgs/{orgs['a'].pk}/members/{member['id']}/",
            {"last_name": "  "},
            content_type=JSON,
        )
        assert resp.status_code == 400

    def test_liste_mit_filter(self, api, orgs, types, board_a):
        c = api(board_a)
        assert admit_org(c, orgs["a"], types["a"]["foerder"]).status_code == 201
        assert admit(c, orgs["a"], types["a"]["aktiv"]).status_code == 201
        url = f"/api/orgs/{orgs['a'].pk}/members/"
        rows = c.get(url, {"typ": "organisation"}).json()["results"]
        assert [(r["kind"], r["last_name"]) for r in rows] == [("organization", "Musterbau GmbH")]
        rows = c.get(url, {"typ": "person"}).json()["results"]
        assert [r["kind"] for r in rows] == ["person"]
        rows = c.get(url, {"geschlecht": "ohne"}).json()["results"]
        assert [r["kind"] for r in rows] == ["person"]


class TestBeitrag:
    def test_ohne_altersstufe(self, orgs, types):
        org, foerder = orgs["a"], types["a"]["foerder"]
        FeeRate.objects.create(organization=org, member_type=foerder, amount=Decimal("120.00"))
        AgeRate.objects.create(organization=org, name="Jugend", max_age=17, amount=Decimal("10.00"))
        assert yearly_fee(org, foerder, None, 2026) == (Decimal("120.00"), "")


class TestLoeschfrist:
    def test_identitaet_ohne_geburtsdatum(self, api, orgs, types, board_a):
        from members.workflows import _reduce_identity

        member = admit_org(api(board_a), orgs["a"], types["a"]["foerder"]).json()
        membership = Membership.objects.get(pk=member["id"])
        _reduce_identity(membership.person)
        person = Person.objects.get()
        assert person.birth_date is None
        assert person.last_name == "Musterbau GmbH"
