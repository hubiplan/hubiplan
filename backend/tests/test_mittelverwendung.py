"""Mittelverwendungsrechnung (Konzept vereinskasse-steuern, S5); erfundene Daten."""

import datetime
from decimal import Decimal

import pytest

from core.tenancy import tenant_context
from finance import use_of_funds
from finance.models import Account, Booking, Category, Reserve, ReserveMovement

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


def buchen(club, account, cat, year, number, amount, kind):
    with tenant_context(club.pk):
        Booking.objects.create(
            organization=club,
            year=year,
            number=number,
            date=D(year, 3, number),
            kind=kind,
            amount=Decimal(amount),
            account=account,
            category=cat,
            text="Muster",
        )


def test_vortrag_aelteste_mittel_zuerst(club, kasse):
    account, cats = kasse
    # 2022: 10.000 € Beiträge, 4.000 € verwendet -> 6.000 € Vortrag aus 2022
    buchen(club, account, cats["ideal"], 2022, 1, "10000", "income")
    buchen(club, account, cats["ideal"], 2022, 2, "4000", "expense")
    # 2023: 5.000 € Beiträge, Fest mit 1.000 € Überschuss, 3.000 € verwendet,
    # 2.000 € in eine Rücklage
    buchen(club, account, cats["ideal"], 2023, 1, "5000", "income")
    buchen(club, account, cats["business"], 2023, 2, "3000", "income")
    buchen(club, account, cats["business"], 2023, 3, "2000", "expense")
    buchen(club, account, cats["ideal"], 2023, 4, "3000", "expense")
    with tenant_context(club.pk):
        reserve = Reserve.objects.create(organization=club, name="Dach", kind="purpose")
        ReserveMovement.objects.create(
            organization=club,
            reserve=reserve,
            direction="add",
            date=D(2023, 12, 31),
            year=2023,
            amount=Decimal("2000"),
        )
    data = use_of_funds.report(club, 2024)
    y2023 = next(r for r in data["years"] if r["year"] == 2023)
    assert y2023["inflow"] == Decimal("6000")
    assert y2023["carry_in"] == Decimal("6000")
    assert y2023["carry_out"] == Decimal("7000")
    # 5.000 € aus 2022 verbraucht, 1.000 € aus 2022 und 6.000 € aus 2023 übrig
    origins = {o["year"]: o for o in data["by_origin"]}
    assert origins[2022]["amount"] == Decimal("1000")
    assert origins[2022]["due_now"] is True and origins[2022]["overdue"] is False
    assert origins[2023]["amount"] == Decimal("6000")
    assert data["due_now"] == Decimal("1000")
    assert use_of_funds.report(club, 2025)["overdue"] == Decimal("1000")


def test_api_nur_mit_modul(api, board_a, club, kasse):
    c = api(board_a)
    url = f"/api/orgs/{club.pk}/finance/use-of-funds/"
    resp = c.get(url, {"jahr": 2025})
    assert resp.status_code == 200, resp.content
    assert resp.json()["year"] == 2025
    club.enabled_modules = ["finance", "members"]
    club.save()
    assert c.get(url).status_code == 404
