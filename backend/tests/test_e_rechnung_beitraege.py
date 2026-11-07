# ruff: noqa: F811
"""Beitragsrechnungen als XRechnung an Mitglieder mit Leitweg-ID (Konzept J8a).

Die Prüfung läuft mit dem echten KoSIT-Prüfwerkzeug (wie test_einvoice_workflow)."""

import xml.etree.ElementTree as ET
from decimal import Decimal

import pytest
from django.core import mail

from billing import einvoice_services, member_einvoice
from billing.models import Invoice, InvoiceArtifact
from core.tenancy import tenant_context
from members.models import BillingAddress, Membership
from organizations.models import Imprint

from .test_m9_billing import _private, base, c, club, setup, zug  # noqa: F401
from .test_organisationsmitglieder import admit_org

pytestmark = pytest.mark.django_db
JSON = "application/json"
UBL = {
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
}


@pytest.fixture
def einvoice(club, c, base, setup):
    club.street, club.postal_code, club.city = "Vereinsweg 1", "12345", "Musterstadt"
    club.contact_phone = "+49 30 123456"
    club.save()
    Imprint.objects.create(
        organization=club,
        mode="text",
        registered=True,
        register_court="Amtsgericht Musterstadt",
        register_number="VR 1234",
    )
    resp = c.patch(
        f"{base}/settings/",
        {"einvoice_members": True, "einvoice_contact": "Karla Kasse"},
        content_type=JSON,
    )
    assert resp.status_code == 200, resp.json()
    assert resp.json()["einvoice_members"] is True


@pytest.fixture
def behoerde(club, c, setup):
    resp = admit_org(
        c,
        club,
        setup["aktiv"],
        last_name="Stadt Musterstadt",
        name_suffix="",
        legal_form="gebiet",
        vat_id="",
    )
    assert resp.status_code == 201, resp.json()
    membership = Membership.objects.get(pk=resp.json()["id"])
    with tenant_context(club.pk):
        BillingAddress.objects.create(
            organization=club,
            membership=membership,
            name="Stadt Musterstadt – Kämmerei",
            street="Rathausplatz 1",
            postal_code="12345",
            city="Musterstadt",
            email="rechnung@musterstadt.example",
            leitweg_id="991-12345-67",
            order_reference="BE-2025-17",
        )
    return membership


def make_invoice(c, base, membership, lines):
    resp = c.post(
        f"{base}/invoices/",
        {
            "recipient_kind": "member",
            "membership": membership.pk,
            "date": "2025-03-01",
            "subject": "Mitgliedsbeitrag 2025",
            "lines": lines,
        },
        content_type=JSON,
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()["id"]


def xml_of(invoice):
    return ET.fromstring(einvoice_services.read_artifact(invoice))  # noqa: S314 - selbst erzeugt


class TestXRechnungFuerBeitraege:
    def test_festschreiben_erzeugt_gepruefte_xrechnung(self, club, c, base, einvoice, behoerde):
        pk = make_invoice(c, base, behoerde, [{"text": "Jahresbeitrag", "amount": "120.00"}])
        resp = c.post(f"{base}/invoices/{pk}/finalize/")
        assert resp.status_code == 200, resp.json()
        with tenant_context(club.pk):
            invoice = Invoice.objects.get(pk=pk)
            artifact = InvoiceArtifact.objects.get(invoice=invoice)
            assert artifact.report["status"] == "valid", artifact.report
            root = xml_of(invoice)
        assert root.findtext("cbc:BuyerReference", namespaces=UBL) == "991-12345-67"
        assert root.findtext("cac:OrderReference/cbc:ID", namespaces=UBL) == "BE-2025-17"
        endpoint = root.find("cac:AccountingCustomerParty/cac:Party/cbc:EndpointID", UBL)
        assert (endpoint.text, endpoint.get("schemeID")) == ("991-12345-67", "0204")
        assert root.findtext(".//cac:ClassifiedTaxCategory/cbc:ID", namespaces=UBL) == "O"
        assert root.findtext(".//cac:PartyIdentification/cbc:ID", namespaces=UBL) == (
            "Amtsgericht Musterstadt VR 1234"
        )
        assert invoice.total == Decimal("120.00")
        assert invoice.electronic_data["source"] == "membership"
        # Die Rechnungsmail trägt das XML
        mail.outbox.clear()
        assert c.post(f"{base}/invoices/{pk}/send/").status_code == 200
        names = [a[0] for a in mail.outbox[0].attachments]
        assert names[0].endswith(".xml") and names[1].endswith(".pdf")

    def test_steuerpflichtiger_posten(self, club, c, base, einvoice, behoerde):
        c.patch(
            f"{base}/settings/",
            {"vat_enabled": True, "tax_number": "DE987654321"},
            content_type=JSON,
        )
        pk = make_invoice(
            c,
            base,
            behoerde,
            [
                {"text": "Jahresbeitrag", "amount": "100.00"},
                {"text": "Anzeige in der Festschrift", "amount": "119.00", "vat_rate": "19.00"},
            ],
        )
        resp = c.post(f"{base}/invoices/{pk}/finalize/")
        assert resp.status_code == 200, resp.json()
        with tenant_context(club.pk):
            invoice = Invoice.objects.get(pk=pk)
            assert InvoiceArtifact.objects.get(invoice=invoice).report["status"] == "valid"
            root = xml_of(invoice)
        categories = {
            node.text for node in root.findall(".//cac:ClassifiedTaxCategory/cbc:ID", UBL)
        }
        assert categories == {"S", "E"}
        assert invoice.total == Decimal("219.00")

    def test_ohne_leitweg_id_bleibt_es_eine_normale_rechnung(
        self, club, c, base, einvoice, behoerde
    ):
        with tenant_context(club.pk):
            BillingAddress.objects.filter(membership=behoerde).update(leitweg_id="")
        pk = make_invoice(c, base, behoerde, [{"text": "Jahresbeitrag", "amount": "120.00"}])
        assert c.post(f"{base}/invoices/{pk}/finalize/").status_code == 200
        with tenant_context(club.pk):
            assert Invoice.objects.get(pk=pk).electronic_data == {}

    def test_ausgeschaltet_keine_e_rechnung(self, club, c, base, setup, behoerde):
        pk = make_invoice(c, base, behoerde, [{"text": "Jahresbeitrag", "amount": "120.00"}])
        assert c.post(f"{base}/invoices/{pk}/finalize/").status_code == 200
        with tenant_context(club.pk):
            assert Invoice.objects.get(pk=pk).electronic_data == {}

    def test_fehlende_angaben_verhindern_festschreiben(self, club, c, base, setup, behoerde):
        c.patch(f"{base}/settings/", {"einvoice_members": True}, content_type=JSON)
        pk = make_invoice(c, base, behoerde, [{"text": "Jahresbeitrag", "amount": "120.00"}])
        resp = c.post(f"{base}/invoices/{pk}/finalize/")
        assert resp.status_code == 400
        assert "Beitragseinstellungen" in str(resp.json())
        with tenant_context(club.pk):
            invoice = Invoice.objects.get(pk=pk)
            assert invoice.status == Invoice.Status.DRAFT
            assert invoice.electronic_data == {}


def test_laendercode():
    assert member_einvoice.country_code("") == "DE"
    assert member_einvoice.country_code("Österreich") == "AT"
    assert member_einvoice.country_code("nl") == "NL"
    assert member_einvoice.country_code("Atlantis") == "DE"
