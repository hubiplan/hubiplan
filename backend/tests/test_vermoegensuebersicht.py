"""Vermögensübersicht zum Jahresende (Konzept vereinskasse-steuern, S7); erfundene Daten."""

import datetime
from decimal import Decimal

import pytest

from billing.models import IncomingInvoice, Invoice, Payment
from core.tenancy import tenant_context
from finance import net_assets, report
from finance.models import Account, Booking, Category, FixedAsset, Reserve, ReserveMovement

from .factories import make_member

pytestmark = pytest.mark.django_db
D = datetime.date


@pytest.fixture
def club(orgs):
    club = orgs["a"]
    club.enabled_modules = ["finance", "members", "billing", "tax"]
    club.reserves_enabled = True
    club.save()
    return club


@pytest.fixture
def daten(club):
    member = make_member(club, "Erika", "Musterfrau")
    with tenant_context(club.pk):
        account = Account.objects.create(
            organization=club,
            name="Girokonto",
            kind="bank",
            opening_date=D(2024, 1, 1),
            opening_balance=Decimal("5000"),
        )
        cat = Category.objects.create(organization=club, name="Beiträge")
        # Rechnung 2025 über 120 €, bezahlt erst im Januar 2026: am 31.12.2025 offen
        invoice = Invoice.objects.create(
            organization=club,
            membership=member,
            recipient_kind="member",
            recipient_name="Erika Musterfrau",
            date=D(2025, 11, 1),
            due_date=D(2025, 11, 15),
            year=2025,
            number=1,
            status="paid",
            total=Decimal("120.00"),
            paid=Decimal("120.00"),
        )
        booking = Booking.objects.create(
            organization=club,
            year=2026,
            number=1,
            date=D(2026, 1, 10),
            kind="income",
            amount=Decimal("120"),
            account=account,
            category=cat,
            text="Beitrag",
        )
        Payment.objects.create(
            organization=club,
            invoice=invoice,
            date=D(2026, 1, 10),
            amount=Decimal("120"),
            method="transfer",
            booking=booking,
        )
        # Eingangsrechnung Dezember 2025, noch nicht bezahlt
        IncomingInvoice.objects.create(
            organization=club,
            original="erechnungen/beispiel.xml",
            name="beispiel.xml",
            sha256="0" * 64,
            content_type="application/xml",
            status="approved",
            data={
                "seller": "Zeltverleih Muster",
                "number": "ZV-77",
                "date": "2025-12-20",
                "due_date": "2026-01-19",
                "payable": "450.00",
                "currency": "EUR",
            },
        )
        FixedAsset.objects.create(
            organization=club,
            name="Festzelt",
            acquired_on=D(2025, 4, 10),
            cost=Decimal("12000"),
            method="linear",
            useful_life=10,
            tax_area="business",
        )
        reserve = Reserve.objects.create(organization=club, name="Neues Dach", kind="purpose")
        ReserveMovement.objects.create(
            organization=club,
            reserve=reserve,
            direction="add",
            date=D(2025, 12, 31),
            year=2025,
            amount=Decimal("2000"),
        )
    return account


def test_vermoegen_zum_stichtag(club, daten):
    data = net_assets.report(club, 2025)
    assert data["cash"] == Decimal("5000")
    assert data["receivables"] == {"total": Decimal("120.00"), "count": 1}
    assert data["liabilities"]["total"] == Decimal("450.00")
    assert data["liabilities"]["items"][0]["seller"] == "Zeltverleih Muster"
    # Festzelt: 12.000 € abzüglich 9 Monate AfA (900 €)
    assert data["fixed_assets"] == {"total": Decimal("11100.00"), "count": 1}
    assert data["net"] == Decimal("5000") + Decimal("120") + Decimal("11100") - Decimal("450")
    assert data["reserves"]["total"] == Decimal("2000")
    assert data["free"] == data["net"] - Decimal("2000")
    # Ein Jahr später ist die Rechnung bezahlt
    later = net_assets.report(club, 2026)
    assert later["receivables"]["count"] == 0
    assert later["cash"] == Decimal("5120")


def test_api_und_kassenbericht(api, board_a, club, daten):
    resp = api(board_a).get(f"/api/orgs/{club.pk}/finance/net-assets/", {"jahr": 2025})
    assert resp.status_code == 200, resp.content
    assert resp.json()["net"] == "15770.00"
    pdf = report.render(club, 2025)
    assert pdf.startswith(b"%PDF")


def test_ohne_kasse_kein_zugriff(api, board_c, club):
    resp = api(board_c).get(f"/api/orgs/{club.pk}/finance/net-assets/")
    assert resp.status_code in (403, 404)
