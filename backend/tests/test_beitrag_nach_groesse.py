# ruff: noqa: F811
"""Beitrag nach Größe für Organisationsmitglieder (Konzept J8c)."""

from decimal import Decimal

import pytest

from billing.models import Invoice, SizeRate
from billing.services import yearly_fee
from core.tenancy import tenant_context
from members.models import Membership

from .factories import make_member
from .test_m9_billing import JSON, _private, base, c, club, setup, start_run, zug  # noqa: F401
from .test_organisationsmitglieder import admit_org

pytestmark = pytest.mark.django_db


def stufe(c, base, **data):
    return c.post(f"{base}/size-rates/", data, content_type=JSON)


class TestStaffelNachGroesse:
    def test_stufen_anlegen_und_pruefen(self, c, base, setup):
        resp = stufe(c, base, name="bis 50", max_size=50, amount="100.00")
        assert resp.status_code == 201, resp.json()
        assert stufe(c, base, name="leer", amount="10.00").status_code == 400
        resp = stufe(c, base, name="falsch", min_size=10, max_size=5, amount="10.00")
        assert resp.status_code == 400
        resp = stufe(c, base, name="über", min_size=40, max_size=100, amount="200.00")
        assert resp.status_code == 400
        assert "bis 50" in str(resp.json())
        assert stufe(c, base, name="ab 51", min_size=51, amount="250.00").status_code == 201
        rows = c.get(f"{base}/size-rates/").json()
        assert [r["name"] for r in rows] == ["bis 50", "ab 51"]

    def test_groesse_in_der_akte(self, club, c, setup):
        resp = admit_org(c, club, setup["aktiv"], size=120)
        assert resp.status_code == 201, resp.json()
        data = resp.json()
        assert data["organization"]["size"] == 120
        resp = c.patch(
            f"/api/orgs/{club.pk}/members/{data['id']}/", {"size": 80}, content_type=JSON
        )
        assert resp.status_code == 200, resp.json()
        assert resp.json()["organization"]["size"] == 80
        # ein geleertes Eingabefeld heißt „keine Größe“
        resp = c.patch(
            f"/api/orgs/{club.pk}/members/{data['id']}/", {"size": ""}, content_type=JSON
        )
        assert resp.status_code == 200, resp.json()
        assert resp.json()["organization"]["size"] is None

    def test_personen_haben_keine_groesse(self, club, c, setup):
        erika = make_member(club, "Erika", "Muster")
        with tenant_context(club.pk):
            assert Membership.objects.get(pk=erika.pk).person.size is None

    def test_beitragslauf_nach_groesse(self, club, c, base, setup):
        assert stufe(c, base, name="bis 50", max_size=50, amount="100.00").status_code == 201
        assert stufe(c, base, name="ab 51", min_size=51, amount="250.00").status_code == 201
        assert admit_org(c, club, setup["aktiv"], size=120).status_code == 201
        resp = admit_org(c, club, setup["aktiv"], last_name="Klein GmbH", size=8)
        assert resp.status_code == 201, resp.json()
        assert admit_org(c, club, setup["aktiv"], last_name="Ohne GmbH").status_code == 201
        resp = start_run(c, base)
        assert resp.status_code == 201, resp.json()
        with tenant_context(club.pk):
            totals = {i.recipient_name.splitlines()[0]: i.total for i in Invoice.objects.all()}
        assert totals["Musterbau GmbH – Niederlassung Musterstadt"] == Decimal("250.00")
        assert totals["Klein GmbH – Niederlassung Musterstadt"] == Decimal("100.00")
        # ohne Größe gilt der Beitrag der Mitgliedsart
        assert totals["Ohne GmbH – Niederlassung Musterstadt"] == Decimal("60.00")


def test_stufe_der_mitgliedsart_geht_vor(club, setup):
    with tenant_context(club.pk):
        aktiv = setup["aktiv"]
        SizeRate.objects.create(organization=club, name="alle", min_size=1, amount=Decimal(50))
        SizeRate.objects.create(
            organization=club, name="aktiv", min_size=1, member_type=aktiv, amount=Decimal(70)
        )
        assert yearly_fee(club, aktiv, None, 2025, size=10) == (Decimal(70), "aktiv")
        assert yearly_fee(club, setup["passiv"], None, 2025, size=10) == (Decimal(50), "alle")
        assert yearly_fee(club, aktiv, None, 2025) == (Decimal("60.00"), "")
