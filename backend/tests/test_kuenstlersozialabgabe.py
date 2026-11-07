"""Künstlersozialabgabe (Konzept vereinskasse-steuern, S4); erfundene Daten."""

import datetime
from decimal import Decimal

import pytest

from core.tenancy import tenant_context
from finance import artist_fees
from finance.models import Account, Booking, Category

pytestmark = pytest.mark.django_db
JSON = "application/json"
D = datetime.date


@pytest.fixture
def club(orgs):
    club = orgs["a"]
    club.enabled_modules = ["finance", "members", "tax"]
    club.save()
    return club


@pytest.fixture
def c(api, board_a):
    return api(board_a)


@pytest.fixture
def fin(club):
    return f"/api/orgs/{club.pk}/finance"


@pytest.fixture
def kasse(club):
    with tenant_context(club.pk):
        account = Account.objects.create(
            organization=club, name="Girokonto", kind="bank", opening_date=D(2020, 1, 1)
        )
        musik = Category.objects.create(organization=club, name="Musik", artist_fees=True)
        sonst = Category.objects.create(organization=club, name="Vereinsbedarf")
    return account, musik, sonst


def buchen(club, account, cat, number, amount, **kw):
    with tenant_context(club.pk):
        return Booking.objects.create(
            organization=club,
            year=2025,
            number=number,
            date=kw.pop("date", D(2025, 6, number)),
            kind=kw.pop("kind", "expense"),
            amount=Decimal(amount),
            account=account,
            category=cat,
            text=kw.pop("text", "Honorar"),
            **kw,
        )


def test_saetze():
    assert artist_fees.rate(2025) == Decimal("5.0")
    assert artist_fees.rate(2026) == Decimal("4.9")
    assert artist_fees.rate(2027) == Decimal("5.0")
    assert artist_fees.rate(2022) == Decimal("4.2")


def test_summe_aus_kategorie_und_kennzeichen(c, fin, club, kasse):
    account, musik, sonst = kasse
    buchen(club, account, musik, 1, "800", counterparty="Blaskapelle Musterdorf")
    buchen(club, account, sonst, 2, "200", counterparty="DJ Muster", artist_fee=True)
    buchen(club, account, sonst, 3, "50", counterparty="Baumarkt")
    storniert = buchen(club, account, musik, 4, "300", counterparty="Blaskapelle Musterdorf")
    buchen(club, account, musik, 5, "300", kind="income", cancels=storniert)
    data = artist_fees.report(club, 2025)
    assert data["total"] == Decimal("1000")
    assert data["levy"] == Decimal("50.00")
    assert data["over_threshold"] is True
    assert data["due"] == D(2026, 3, 31)
    assert [r["name"] for r in data["recipients"]] == ["Blaskapelle Musterdorf", "DJ Muster"]
    resp = c.get(f"{fin}/artist-fees/", {"jahr": 2025})
    assert resp.status_code == 200
    assert resp.json()["total"] == "1000.00"
    xlsx = c.get(f"{fin}/artist-fees/", {"jahr": 2025, "als": "xlsx"})
    assert xlsx.status_code == 200 and xlsx.content.startswith(b"PK")


def test_kennzeichen_ueber_die_api(c, fin, club, kasse):
    account, _musik, sonst = kasse
    b = buchen(club, account, sonst, 1, "120", counterparty="Grafikbüro Muster")
    resp = c.patch(f"{fin}/bookings/{b.pk}/", {"artist_fee": True}, JSON)
    assert resp.status_code == 200, resp.json()
    assert resp.json()["artist_fee"] is True
    resp = c.patch(f"{fin}/categories/{sonst.pk}/", {"artist_fees": True}, JSON)
    assert resp.status_code == 200, resp.json()
    assert resp.json()["artist_fees"] is True
    # Nur Ausgaben
    e = buchen(club, account, sonst, 2, "40", kind="income", text="Eintritt")
    assert c.patch(f"{fin}/bookings/{e.pk}/", {"artist_fee": True}, JSON).status_code == 400


def test_nur_mit_modul(c, fin, club, kasse):
    club.enabled_modules = ["finance", "members"]
    club.save()
    assert c.get(f"{fin}/artist-fees/").status_code == 404
    account, _musik, sonst = kasse
    b = buchen(club, account, sonst, 1, "120")
    assert c.patch(f"{fin}/bookings/{b.pk}/", {"artist_fee": True}, JSON).status_code == 400
