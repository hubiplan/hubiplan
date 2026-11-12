"""Haushalte und Firmen H2/H3: Zahler, eine Rechnung je Haushalt im Beitragslauf,
Familien- und Firmenbeitrag, Mandat am Haushalt, Mitgliederbereich des Zahlers."""
# ruff: noqa: F811  (Fixtures aus test_m9_billing als Parameter)

import datetime
import uuid
from decimal import Decimal

import pytest

from billing import sepa
from billing.households import fee_discount
from billing.models import HouseholdFeeRule, Invoice
from billing.services import FeeItem, period
from core.tenancy import tenant_context
from finance.models import Booking
from members.models import HouseholdMember
from portal.models import PortalAccess

from .factories import make_member
from .test_m9_billing import _private, base, c, club, setup, start_run, zug  # noqa: F401

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture
def family(club, setup):
    return {
        "erika": make_member(club, "Erika", "Muster", "erika@example.org"),
        "max": make_member(club, "Max", "Muster", "max@example.org"),
        "lisa": make_member(club, "Lisa", "Muster", birth_date=datetime.date(2012, 1, 1)),
        "otto": make_member(club, "Otto", "Other"),
    }


def hh_url(club, pk=None, suffix=""):
    root = f"/api/orgs/{club.pk}/households/"
    return f"{root}{pk}/{suffix}" if pk else root


def household(c, club, family, kind="family", pays_via=True, who=("erika", "max", "lisa")):
    hh = c.post(hh_url(club), {"name": "Familie Muster", "kind": kind}, content_type=JSON).json()
    roles = {"erika": "adult", "max": "adult", "lisa": "child"}
    for key in who:
        resp = c.post(
            hh_url(club, hh["id"], "members/"),
            {
                "membership": family[key].pk,
                "role": roles.get(key, ""),
                "valid_from": "2025-01-01",
                "pays_via": pays_via,
            },
            content_type=JSON,
        )
        assert resp.status_code == 201, resp.json()
    return hh


def set_payer(c, base, hh, **data):
    resp = c.put(f"{base}/households/{hh['id']}/payer/", data, content_type=JSON)
    assert resp.status_code == 200, resp.json()
    return resp.json()


class TestHaushaltsrechnung:
    def test_eine_rechnung_an_den_zahler(self, club, c, base, family):
        hh = household(c, club, family)
        data = set_payer(c, base, hh, kind="member", membership=family["erika"].pk)
        assert data["payer"]["membership_name"]
        preview = c.post(f"{base}/runs/preview/", {"year": 2025, "period": 1}, content_type=JSON)
        assert preview.json()["households"][0]["members"] == 3
        assert preview.json()["checks"]["households"] == 1
        run = start_run(c, base)
        assert run.status_code == 201, run.json()
        invoice = Invoice.objects.get(recipient_kind="household")
        assert invoice.household_id == hh["id"]
        assert invoice.recipient_name.splitlines()[0] == "Erika Muster"
        assert invoice.recipient_email == "erika@example.org"
        assert "Familie Muster" in invoice.subject
        lines = list(invoice.lines.all())
        assert [line.text for line in lines] == ["Muster, Erika", "Muster, Max", "Muster, Lisa"]
        assert invoice.total == Decimal("150.00")  # 60 + 60 + 30 (Jugend)
        # Keine Einzelrechnungen für die drei, Otto wie bisher
        assert not Invoice.objects.filter(membership__in=[family["erika"], family["max"]]).exists()
        assert Invoice.objects.filter(membership=family["otto"]).exists()
        # Zweiter Lauf (Nachzügler): Haushalt gilt als abgerechnet
        c.post(f"{base}/runs/{run.json()['id']}/finalize/")
        assert c.post(f"{base}/runs/{run.json()['id']}/rebuild/").json()["created"] == 0
        pdf = c.get(f"{base}/invoices/{invoice.pk}/pdf/")
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

    def test_ohne_zahler_wie_bisher(self, club, c, base, family):
        household(c, club, family)
        preview = c.post(f"{base}/runs/preview/", {"year": 2025, "period": 1}, content_type=JSON)
        assert preview.json()["checks"]["household_without_payer"] == 3
        start_run(c, base)
        assert not Invoice.objects.filter(recipient_kind="household").exists()
        assert Invoice.objects.filter(membership=family["erika"]).exists()

    def test_ohne_beitrag_ueber_haushalt_wie_bisher(self, club, c, base, family):
        hh = household(c, club, family, pays_via=False)
        set_payer(c, base, hh, kind="member", membership=family["erika"].pk)
        start_run(c, base)
        assert not Invoice.objects.filter(recipient_kind="household").exists()

    def test_familienbeitrag_hoechstbetrag(self, club, c, base, family):
        hh = household(c, club, family)
        set_payer(c, base, hh, kind="member", membership=family["erika"].pk)
        resp = c.put(
            f"{base}/household-fee-rules/",
            {"kind": "family", "mode": "cap", "amount": "100.00"},
            content_type=JSON,
        )
        assert resp.status_code == 200, resp.json()
        assert resp.json()[0]["mode"] == "cap"
        start_run(c, base)
        invoice = Invoice.objects.get(recipient_kind="household")
        assert invoice.total == Decimal("100.00")
        last = list(invoice.lines.all())[-1]
        assert last.text == "Familienbeitrag" and last.amount == Decimal("-50.00")
        assert not last.is_fee

    def test_externer_zahler_mit_mandat_am_haushalt(self, club, c, base, family):
        hh = household(c, club, family)
        resp = c.put(
            f"{base}/households/{hh['id']}/payer/", {"kind": "external"}, content_type=JSON
        )
        assert resp.status_code == 400
        set_payer(
            c,
            base,
            hh,
            kind="external",
            name="Gisela Muster",
            street="Lindenweg 4",
            postal_code="12345",
            city="Musterstadt",
            email="oma@example.org",
        )
        run = start_run(c, base).json()
        c.post(f"{base}/runs/{run['id']}/finalize/")
        invoice = Invoice.objects.get(recipient_kind="household")
        assert invoice.recipient_name == "Gisela Muster"
        assert invoice.recipient_address == "Lindenweg 4\n12345 Musterstadt"
        with tenant_context(club.pk):
            mandate = sepa.create_mandate(
                club,
                household=invoice.household,
                signed_on=datetime.date(2025, 1, 1),
                source="paper",
                user=None,
                holder="Gisela Muster",
                iban="DE89370400440532013000",
            )
            assert mandate.reference.startswith("HAUSH-")
            assert [i.pk for i, _ in sepa.proposals(club)] == [invoice.pk]
        data = c.get(f"{base}/households/{hh['id']}/payer/").json()
        assert data["mandates"][0]["payer_name"] == "Familie Muster"

    def test_beitrag_nur_ueber_einen_haushalt(self, club, c, base, family):
        household(c, club, family, who=("max",))
        firm = c.post(hh_url(club), {"name": "Musterbau", "kind": "company"}, content_type=JSON)
        resp = c.post(
            hh_url(club, firm.json()["id"], "members/"),
            {"membership": family["max"].pk, "valid_from": "2025-01-01", "pays_via": True},
            content_type=JSON,
        )
        assert resp.status_code == 400 and "pays_via" in resp.json()
        resp = c.post(
            hh_url(club, firm.json()["id"], "members/"),
            {"membership": family["max"].pk, "valid_from": "2025-01-01"},
            content_type=JSON,
        )
        assert resp.status_code == 201
        link = resp.json()["members"][0]["link"]
        resp = c.patch(
            hh_url(club, firm.json()["id"], f"members/{link}/"),
            {"pays_via": True},
            content_type=JSON,
        )
        assert resp.status_code == 400
        old = HouseholdMember.objects.get(kind="family")
        c.patch(
            hh_url(club, old.household_id, f"members/{old.pk}/"),
            {"pays_via": False},
            content_type=JSON,
        )
        resp = c.patch(
            hh_url(club, firm.json()["id"], f"members/{link}/"),
            {"pays_via": True},
            content_type=JSON,
        )
        assert resp.status_code == 200 and resp.json()["members"][0]["pays_via"] is True

    def test_mitgliederbereich_des_zahlers(self, club, c, base, family, api):
        hh = household(c, club, family, who=("max", "lisa"))
        set_payer(c, base, hh, kind="member", membership=family["erika"].pk)
        run = start_run(c, base).json()
        c.post(f"{base}/runs/{run['id']}/finalize/")
        invoice = Invoice.objects.get(recipient_kind="household")
        c.post(f"/api/orgs/{club.pk}/members/{family['erika'].pk}/access/")
        access = PortalAccess.objects.get(membership=family["erika"])
        erika = api(access.user)
        data = erika.get(f"/api/portal/{access.pk}/invoices/").json()
        assert sorted(i["id"] for i in data["invoices"]) == sorted(
            [invoice.pk, Invoice.objects.get(membership=family["erika"]).pk]
        )
        assert erika.get(f"/api/portal/{access.pk}/invoices/{invoice.pk}/pdf/").status_code == 200
        # Max sieht seinen Posten, nicht die Rechnung selbst
        c.post(f"/api/orgs/{club.pk}/members/{family['max'].pk}/access/")
        m_access = PortalAccess.objects.get(membership=family["max"])
        data = api(m_access.user).get(f"/api/portal/{m_access.pk}/invoices/").json()
        assert data["invoices"] == []
        assert data["collective"][0]["department_name"] == "Familie Muster"


class TestZuwendungAnZahler:
    def test_zahlung_auf_den_zahler(self, club, c, base, family, setup):
        """FH-15: Zahlung einer Haushaltsrechnung bucht auf den Zahler, nicht auf ein Kind."""
        hh = household(c, club, family, who=("max", "lisa"))
        set_payer(c, base, hh, kind="member", membership=family["erika"].pk)
        run = start_run(c, base).json()
        c.post(f"{base}/runs/{run['id']}/finalize/")
        invoice = Invoice.objects.get(recipient_kind="household")
        resp = c.post(
            f"{base}/invoices/{invoice.pk}/payments/",
            {
                "date": "2025-02-10",
                "amount": "10.00",
                "method": "transfer",
                "account": setup["bank"],
            },
            content_type=JSON,
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert resp.status_code == 200, resp.json()
        with tenant_context(club.pk):
            booking = Booking.objects.get(payment__invoice=invoice)
        assert booking.membership_id == family["erika"].pk

    def test_spender_aus_der_rechnung(self, club, c, base, family, setup):
        hh = household(c, club, family, who=("max", "lisa"))
        set_payer(
            c,
            base,
            hh,
            kind="external",
            name="Gisela Muster",
            street="Ahornweg 2",
            postal_code="12345",
            city="Musterstadt",
        )
        run = start_run(c, base).json()
        c.post(f"{base}/runs/{run['id']}/finalize/")
        invoice = Invoice.objects.get(recipient_kind="household")
        c.post(
            f"{base}/invoices/{invoice.pk}/payments/",
            {
                "date": "2025-02-10",
                "amount": "10.00",
                "method": "transfer",
                "account": setup["bank"],
            },
            content_type=JSON,
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        from finance.donations import _donor_from_invoice

        with tenant_context(club.pk):
            booking = Booking.objects.get(payment__invoice=invoice)
            assert booking.membership_id is None
            name, address = _donor_from_invoice(booking)
        assert name == "Gisela Muster"
        assert "Ahornweg 2" in address


class TestFamilienbeitrag:
    def _items(self, *amounts, roles=None):
        roles = roles or ["adult"] * len(amounts)
        return [
            FeeItem(None, Decimal(a), "", "", household_role=r)
            for a, r in zip(amounts, roles, strict=True)
        ]

    def _p(self, club):
        with tenant_context(club.pk):
            return period(club, 2025, "yearly", 1)

    def test_formen(self, club):
        p = self._p(club)
        rule = HouseholdFeeRule(organization=club, kind="family", mode="cap", amount=Decimal(100))
        assert fee_discount(rule, self._items(60, 60, 30), p)[0] == Decimal("50.00")
        assert fee_discount(rule, self._items(60), p)[0] == Decimal("0")
        rule.mode = "flat"
        rule.amount = Decimal(80)
        assert fee_discount(rule, self._items(60, 30), p)[0] == Decimal("10.00")
        rule.mode = "stagger"
        rule.second_percent = Decimal(50)
        rule.third_percent = Decimal(100)
        discount, detail = fee_discount(rule, self._items(30, 60, 60), p)
        assert discount == Decimal("60.00")  # 60 voll, 60 halb, 30 frei
        assert "50 %" in detail
        rule.adult_required = True
        assert fee_discount(rule, self._items(30, 30, roles=["child", "child"]), p)[0] == 0
        rule.min_persons = 4
        assert fee_discount(rule, self._items(60, 60, 30), p)[0] == 0
