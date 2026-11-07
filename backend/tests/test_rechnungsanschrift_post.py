"""Post und Geld für Organisationsmitglieder (Konzept juristische Personen, J3):
abweichende Rechnungsanschrift, Rechnungsmail, Bestellnummer/Leitweg-ID, Rundschreiben."""

import pytest

from billing.services import member_recipient
from circulars import recipients as rcp
from circulars.models import Circular
from core.tenancy import tenant_context
from finance.donations import donor_from_membership
from members.models import BillingAddress, ContactPerson, Membership

from .test_m2_members import admit, make_types
from .test_organisationsmitglieder import admit_org

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture
def types(orgs):
    return {key: make_types(orgs[key]) for key in ("a", "b")}


@pytest.fixture
def firma(api, orgs, types, board_a):
    resp = admit_org(api(board_a), orgs["a"], types["a"]["foerder"])
    assert resp.status_code == 201, resp.json()
    return Membership.objects.get(pk=resp.json()["id"])


def contact(membership, **kw):
    data = {"organization": membership.organization, "membership": membership}
    data.update(kw)
    return ContactPerson.objects.create(**data)


def recipient(org, membership):
    with tenant_context(org.pk):
        return member_recipient(org, membership)


class TestRechnungsempfaenger:
    def test_organisation_mit_zhd(self, orgs, firma):
        contact(
            firma,
            last_name="Muster",
            first_name="Max",
            email="max@musterbau.example",
            is_primary=True,
            receives_invoices=False,
        )
        contact(firma, last_name="Kasse", first_name="Karla", email="kasse@musterbau.example")
        data = recipient(orgs["a"], firma)
        assert data["recipient_name"] == (
            "Musterbau GmbH – Niederlassung Musterstadt\nz. Hd. Karla Kasse"
        )
        assert data["recipient_address"] == "Musterstraße 1\n12345 Musterstadt"
        assert data["recipient_email"] == "kasse@musterbau.example"

    def test_ohne_ansprechpartner_die_organisation(self, orgs, firma):
        data = recipient(orgs["a"], firma)
        assert data["recipient_name"] == "Musterbau GmbH – Niederlassung Musterstadt"
        assert data["recipient_email"] == "info@musterbau.example"

    def test_abweichende_anschrift(self, api, orgs, firma, board_a):
        contact(firma, last_name="Muster", email="max@musterbau.example", is_primary=True)
        resp = api(board_a).put(
            f"/api/orgs/{orgs['a'].pk}/members/{firma.pk}/billing-address/",
            {
                "name": "Musterbau Holding AG",
                "attention": "Kreditorenbuchhaltung",
                "street": "Postfach 10 20 30",
                "postal_code": "54321",
                "city": "Beispielstadt",
                "email": "rechnung@musterbau.example",
                "order_reference": "PO-4711",
                "leitweg_id": "991-12345-67",
            },
            content_type=JSON,
        )
        assert resp.status_code == 200, resp.json()
        assert resp.json()["billing_address"]["leitweg_id"] == "991-12345-67"
        data = recipient(orgs["a"], firma)
        assert data["recipient_name"] == "Musterbau Holding AG\nKreditorenbuchhaltung"
        assert data["recipient_address"] == "Postfach 10 20 30\n54321 Beispielstadt"
        assert data["recipient_email"] == "rechnung@musterbau.example"
        assert (data["order_reference"], data["leitweg_id"]) == ("PO-4711", "991-12345-67")
        # Zuwendungsbestätigung: immer die Organisation selbst
        with tenant_context(orgs["a"].pk):
            name, address = donor_from_membership(orgs["a"], firma)
        assert name == "Musterbau GmbH – Niederlassung Musterstadt"
        assert address == "Musterstraße 1\n12345 Musterstadt"

    def test_nur_rechnungsmail_ohne_anschrift(self, api, orgs, firma, board_a):
        c = api(board_a)
        url = f"/api/orgs/{orgs['a'].pk}/members/{firma.pk}/billing-address/"
        assert (
            c.put(url, {"email": "rechnung@musterbau.example"}, content_type=JSON).status_code
            == 200
        )
        data = recipient(orgs["a"], firma)
        assert data["recipient_address"] == "Musterstraße 1\n12345 Musterstadt"
        assert data["recipient_email"] == "rechnung@musterbau.example"
        # Unvollständige Anschrift wird abgelehnt
        assert c.put(url, {"city": "Beispielstadt"}, content_type=JSON).status_code == 400
        # Entfernen
        resp = c.delete(url)
        assert resp.status_code == 200 and resp.json()["billing_address"] is None
        assert not BillingAddress.objects.exists()

    def test_auch_fuer_personen(self, api, orgs, types, board_a):
        c = api(board_a)
        kind = admit(c, orgs["a"], types["a"]["aktiv"]).json()
        url = f"/api/orgs/{orgs['a'].pk}/members/{kind['id']}/billing-address/"
        resp = c.put(
            url,
            {
                "name": "Max Muster",
                "street": "Elternweg 2",
                "postal_code": "12345",
                "city": "Musterstadt",
            },
            content_type=JSON,
        )
        assert resp.status_code == 200, resp.json()
        data = recipient(orgs["a"], Membership.objects.get(pk=kind["id"]))
        assert data["recipient_name"] == "Max Muster"
        assert data["recipient_address"] == "Elternweg 2\n12345 Musterstadt"

    def test_anderer_verein_darf_nicht(self, api, orgs, firma, board_b):
        resp = api(board_b).put(
            f"/api/orgs/{orgs['a'].pk}/members/{firma.pk}/billing-address/",
            {"email": "x@example.org"},
            content_type=JSON,
        )
        assert resp.status_code in (403, 404)


class TestRundschreiben:
    def circular(self, org):
        return Circular.objects.create(organization=org, subject="Info", body="{Anrede}")

    def select(self, org):
        with tenant_context(org.pk):
            circular = self.circular(org)
            selection = rcp.select(circular)
            rcp.fill_values(circular, selection, {"Anrede", "Organisation"})
        return selection

    def test_an_ansprechpartner_mit_rundschreiben(self, orgs, firma):
        contact(
            firma,
            last_name="Muster",
            first_name="Erika",
            gender="weiblich",
            email="erika@musterbau.example",
            is_primary=True,
        )
        contact(firma, last_name="Zwei", email="zwei@musterbau.example")
        contact(firma, last_name="Ohne", email="ohne@musterbau.example", receives_mail=False)
        rows = [c for c in self.select(orgs["a"]).candidates if c.membership_id == firma.pk]
        assert [r.email for r in rows] == ["erika@musterbau.example", "zwei@musterbau.example"]
        assert rows[0].key == f"m{firma.pk}" and rows[1].key != rows[0].key
        assert rows[0].values["Anrede"] == "Sehr geehrte Frau Muster"
        assert rows[0].values["Organisation"] == "Musterbau GmbH – Niederlassung Musterstadt"

    def test_ohne_ansprechpartner_an_die_organisation(self, orgs, firma):
        (row,) = [c for c in self.select(orgs["a"]).candidates if c.membership_id == firma.pk]
        assert row.email == "info@musterbau.example"
        assert row.values["Anrede"] == "Sehr geehrte Damen und Herren"

    def test_brief_mit_zhd(self, orgs, firma):
        from members.models import ContactDetails

        ContactDetails.objects.filter(person=firma.person).update(email="")
        contact(firma, last_name="Muster", first_name="Max", is_primary=True)
        (row,) = [c for c in self.select(orgs["a"]).candidates if c.membership_id == firma.pk]
        assert row.channel == "letter"
        assert row.address.splitlines()[:2] == [
            "Musterbau GmbH – Niederlassung Musterstadt",
            "z. Hd. Max Muster",
        ]
