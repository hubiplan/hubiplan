# ruff: noqa: F811
"""Firmenlastschrift (SEPA B2B) für Organisationsmitglieder (Konzept J8b)."""

from xml.etree import ElementTree as ET

import pytest

from billing import sepa
from billing.models import Mandate
from core.tenancy import tenant_context
from members.models import Membership

from .factories import make_member
from .test_m2_members import make_types
from .test_m11_sepa_abschluss import (  # noqa: F401
    JSON,
    NS,
    _private,
    base,
    c,
    club,
    fin,
    next_workday,
    open_invoice,
    setup,
)
from .test_organisationsmitglieder import admit_org

pytestmark = pytest.mark.django_db


@pytest.fixture
def firma(c, club):
    types = make_types(club)
    resp = admit_org(c, club, types["foerder"])
    assert resp.status_code == 201, resp.json()
    return Membership.objects.get(pk=resp.json()["id"])


def mandate(c, base, member, holder, scheme=None):
    data = {
        "membership": member.pk,
        "holder": holder,
        "iban": "DE02120300000000202051",
        "signed_on": "2025-01-10",
    }
    if scheme:
        data["scheme"] = scheme
    return c.post(f"{base}/mandates/", data, content_type=JSON)


class TestFirmenlastschrift:
    def test_b2b_mandat_fuer_organisation(self, c, base, setup, club, firma):
        resp = mandate(c, base, firma, "Musterbau GmbH", "B2B")
        assert resp.status_code == 201, resp.json()
        data = resp.json()
        assert (data["scheme"], data["scheme_label"]) == ("B2B", "Firmenlastschrift")
        assert data["payer_name"] == "Musterbau GmbH – Niederlassung Musterstadt"

    def test_b2b_nicht_fuer_personen(self, c, base, setup, club):
        erika = make_member(club, "Erika", "Muster")
        resp = mandate(c, base, erika, "Erika Muster", "B2B")
        assert resp.status_code == 400
        assert "scheme" in resp.json()
        assert not Mandate.objects.exists()

    def test_vorgabe_bleibt_basislastschrift(self, c, base, setup, club, firma):
        assert mandate(c, base, firma, "Musterbau GmbH").json()["scheme"] == "CORE"

    def test_lauf_mit_getrennten_bloecken(self, c, base, setup, club, firma):
        erika = make_member(club, "Erika", "Muster", "erika@example.org")
        assert mandate(c, base, erika, "Erika Muster").status_code == 201
        assert mandate(c, base, firma, "Musterbau GmbH", "B2B").status_code == 201
        invoices = [open_invoice(c, base, erika), open_invoice(c, base, firma, "250.00")]
        resp = c.post(
            f"{base}/debits/",
            {"invoices": invoices, "collection_date": str(next_workday(6))},
            content_type=JSON,
        )
        assert resp.status_code == 201, resp.json()
        xml = c.get(f"{base}/debits/{resp.json()['id']}/xml/")
        root = ET.fromstring(xml.content)  # noqa: S314 (eigene Ausgabe)
        blocks = {
            info.find("p:PmtTpInf/p:LclInstrm/p:Cd", NS).text: [
                n.text for n in info.findall("p:DrctDbtTxInf/p:Dbtr/p:Nm", NS)
            ]
            for info in root.findall("p:CstmrDrctDbtInitn/p:PmtInf", NS)
        }
        assert blocks == {"CORE": ["Erika Muster"], "B2B": ["Musterbau GmbH"]}
        ids = [n.text for n in root.findall("p:CstmrDrctDbtInitn/p:PmtInf/p:PmtInfId", NS)]
        assert len(set(ids)) == 2

    def test_mandatstext(self, club):
        with tenant_context(club.pk):
            text = sepa.mandate_text(club, "DE98ZZZ09999999999", "MITGL-1-1", sepa.B2B)
        assert "Konten von Unternehmen" in text
        assert "acht Wochen" not in text
