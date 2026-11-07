"""Höchstbetrag der freien Rücklage und Vorschlag Wiederbeschaffung (Konzept
vereinskasse-steuern, S5); erfundene Daten."""

import datetime
from decimal import Decimal

import pytest

from core.tenancy import tenant_context
from finance import reserve_limits
from finance.models import (
    Account,
    Booking,
    Category,
    FixedAsset,
    Reserve,
    ReserveMovement,
)

pytestmark = pytest.mark.django_db
D = datetime.date


@pytest.fixture
def club(orgs):
    club = orgs["a"]
    club.enabled_modules = ["finance", "members", "tax"]
    club.reserves_enabled = True
    club.save()
    return club


@pytest.fixture
def kasse(club):
    with tenant_context(club.pk):
        account = Account.objects.create(
            organization=club, name="Girokonto", kind="bank", opening_date=D(2020, 1, 1)
        )
        cats = {
            area: Category.objects.create(organization=club, name=area, tax_area=area)
            for area in ("ideal", "assets", "purpose", "business")
        }
    return account, cats


def buchen(club, account, cat, number, amount, kind, year=2025):
    with tenant_context(club.pk):
        Booking.objects.create(
            organization=club,
            year=year,
            number=number,
            date=D(year, 3, 1),
            kind=kind,
            amount=Decimal(amount),
            account=account,
            category=cat,
            text="Muster",
        )


def zufuehren(club, reserve, year, amount):
    with tenant_context(club.pk):
        ReserveMovement.objects.create(
            organization=club,
            reserve=reserve,
            direction="add",
            date=D(year, 12, 31),
            year=year,
            amount=Decimal(amount),
        )


def test_hoechstbetrag_und_nachholung(club, kasse):
    account, cats = kasse
    # 2024: Zinsen 300 €, Beiträge 5.000 € -> 100 + 500 = 600 €
    buchen(club, account, cats["assets"], 1, "300", "income", 2024)
    buchen(club, account, cats["ideal"], 2, "5000", "income", 2024)
    # 2025: Zinsen 600 €, Beiträge 4.000 €, Fest 3.000 € Einnahmen und 2.000 € Ausgaben,
    # Zweckbetrieb mit Verlust zählt nicht
    buchen(club, account, cats["assets"], 1, "600", "income")
    buchen(club, account, cats["ideal"], 2, "4000", "income")
    buchen(club, account, cats["business"], 3, "3000", "income")
    buchen(club, account, cats["business"], 4, "2000", "expense")
    buchen(club, account, cats["purpose"], 5, "100", "expense")
    with tenant_context(club.pk):
        frei = Reserve.objects.create(organization=club, name="Freie Rücklage", kind="free")
    zufuehren(club, frei, 2024, "200")
    zufuehren(club, frei, 2025, "1000")

    data = reserve_limits.free_reserve(club, 2025)
    assert data["assets_surplus"] == Decimal("600")
    assert data["other_funds"] == Decimal("5000")
    assert data["limit"] == Decimal("700.00")
    # Rest aus 2024: 600 - 200 = 400 €
    assert data["carry"] == Decimal("400.00")
    assert data["available"] == Decimal("1100.00")
    assert data["over"] == Decimal("0")

    zufuehren(club, frei, 2025, "150")
    assert reserve_limits.free_reserve(club, 2025)["over"] == Decimal("50.00")


def test_vorschlag_wiederbeschaffung_und_api(api, board_a, club, kasse):
    with tenant_context(club.pk):
        FixedAsset.objects.create(
            organization=club,
            name="Festzelt",
            acquired_on=D(2025, 1, 10),
            cost=Decimal("12000"),
            method="linear",
            useful_life=10,
            tax_area="business",
        )
    resp = api(board_a).get(f"/api/orgs/{club.pk}/finance/reserves/limits/", {"jahr": 2025})
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["replacement"] == {"depreciation": "1200.00", "added": "0.00"}
    assert body["free"]["limit"] == "0.00"
    assert body["use_of_funds"] is False


def test_mittelverwendungsrechnung_ab_100000(club, kasse):
    account, cats = kasse
    buchen(club, account, cats["ideal"], 1, "100000", "income")
    assert reserve_limits.report(club, 2025)["use_of_funds"] is True
