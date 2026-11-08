"""Umsatzsteuer in der Kasse (Konzept vereinskasse-steuern, S2): Steuersatz je Buchung,
Vorsteuer, Voranmeldung, § 23a UStG und DATEV-Schlüssel (erfundene Daten)."""

import datetime
from decimal import Decimal

import pytest

from core.tenancy import tenant_context
from finance import datev, vat
from finance.models import Account, Booking, Category

pytestmark = pytest.mark.django_db
JSON = "application/json"
DAY = datetime.date(2026, 2, 10)


@pytest.fixture
def club(orgs):
    club = orgs["a"]
    club.enabled_modules = ["finance", "members", "billing", "tax"]
    club.tax_areas_enabled = True
    club.save()
    return club


@pytest.fixture
def c(api, board_a):
    return api(board_a)


class Kasse:
    def __init__(self, org):
        self.org = org
        self.number = 0
        with tenant_context(org.pk):
            self.account = Account.objects.create(
                organization=org, name="Kasse", kind="cash", opening_date=datetime.date(2020, 1, 1)
            )
            self.cats = {
                area: Category.objects.create(
                    organization=org, name=f"Bereich {area or 'ohne'}", tax_area=area
                )
                for area in ("ideal", "assets", "purpose", "business", "")
            }

    def buchen(self, area, amount, rate, kind="income", day=DAY, share=100, cancels=None):
        self.number += 1
        with tenant_context(self.org.pk):
            return Booking.objects.create(
                organization=self.org,
                year=day.year,
                number=self.number,
                date=day,
                kind=kind,
                amount=Decimal(amount),
                account=self.account,
                category=self.cats[area],
                text="Testbuchung",
                vat_rate=rate,
                input_tax_share=share,
                cancels=cancels,
            )


def get(c, org, **params):
    resp = c.get(f"/api/orgs/{org.pk}/finance/vat/", {"jahr": 2026, **params})
    assert resp.status_code == 200, resp.content
    return resp.json()


def lines(data):
    return {line["code"]: line for line in data["lines"]}


def test_netto_und_steuer_aus_brutto():
    assert vat.split(Decimal("119.00"), "19") == (Decimal("100.00"), Decimal("19.00"))
    assert vat.split(Decimal("10.00"), "7") == (Decimal("9.35"), Decimal("0.65"))
    assert vat.split(Decimal("50.00"), "exempt") == (Decimal("50.00"), Decimal("0.00"))
    assert vat.period_range(2026, "quarter", 4) == (
        datetime.date(2026, 10, 1),
        datetime.date(2026, 12, 31),
    )
    assert vat.period_range(2026, "month", 2)[1] == datetime.date(2026, 2, 28)


def test_voranmeldung_je_quartal(c, club):
    k = Kasse(club)
    k.buchen("business", "119.00", "19")
    k.buchen("purpose", "107.00", "7")
    k.buchen("business", "50.00", "exempt")
    k.buchen("business", "119.00", "19", kind="expense")
    k.buchen("business", "119.00", "19", kind="expense", share=50)
    # Ideeller Bereich: keine Vorsteuer
    k.buchen("ideal", "119.00", "19", kind="expense")
    # Storno einer Einnahme mindert die Umsatzsteuer
    wrong = k.buchen("business", "238.00", "19")
    k.buchen("business", "238.00", "", kind="expense", cancels=wrong)
    # Anderes Quartal zählt nicht
    k.buchen("business", "119.00", "19", day=datetime.date(2026, 5, 2))
    data = get(c, club, art="quarter", zeitraum=1)
    assert data["label"] == "1. Quartal 2026"
    by = lines(data)
    assert by["81"]["base"] == "100.00" and by["81"]["tax"] == "19.00"
    assert by["81"]["base_euros"] == 100
    assert by["86"]["base"] == "100.00" and by["86"]["tax"] == "7.00"
    assert by["48"]["base"] == "50.00"
    assert by["66"]["tax"] == "28.50"
    assert by["83"]["tax"] == "-2.50"
    assert data["warnings"][0]["kind"] == "small"


def test_vorsteuerpauschale_und_grenze(c, club):
    k = Kasse(club)
    k.buchen("business", "119.00", "19")
    k.buchen("business", "107.00", "7")
    k.buchen("business", "119.00", "19", kind="expense")
    fin = f"/api/orgs/{club.pk}/finance/settings/"
    assert c.patch(fin, {"vat_flat_rate": True}, content_type=JSON).status_code == 200
    data = get(c, club, art="year")
    by = lines(data)
    assert data["flat_rate_used"] is True
    assert "66" not in by and by["63"]["tax"] == "14.00"
    assert by["83"]["tax"] == "12.00"
    # Vorjahr über 50.000 € steuerpflichtige Umsätze: Pauschale nicht zulässig
    k.buchen("business", "59501.19", "19", day=datetime.date(2025, 6, 1))
    data = get(c, club, art="year")
    assert data["flat_rate_used"] is False
    assert lines(data)["66"]["tax"] == "19.00"
    assert "flat" in {w["kind"] for w in data["warnings"]}


def test_einstellungen_und_hinweise(c, club):
    fin = f"/api/orgs/{club.pk}/finance/settings/"
    resp = c.patch(fin, {"vat_registered": True}, content_type=JSON)
    assert resp.status_code == 200 and resp.json()["vat_registered"] is True
    resp = c.patch(fin, {"vat_period": "month"}, content_type=JSON)
    assert resp.json()["vat_period"] == "month"
    assert c.patch(fin, {"vat_period": "woche"}, content_type=JSON).status_code == 400
    k = Kasse(club)
    k.buchen("ideal", "119.00", "19")
    data = get(c, club, zeitraum=2)
    assert data["period"] == "month" and data["label"] == "02/2026"
    assert len(data["periods"]) == 12
    assert {w["kind"] for w in data["warnings"]} == {"ideal"}


def test_vorgabe_der_kategorie_und_umbuchung(c, club):
    k = Kasse(club)
    with tenant_context(club.pk):
        cat = k.cats["business"]
        cat.vat_rate = "19"
        cat.save()
    base = f"/api/orgs/{club.pk}/finance/bookings/"
    body = {
        "date": "2026-02-10",
        "kind": "income",
        "amount": "119.00",
        "account": k.account.pk,
        "category": cat.pk,
        "text": "Getränkeverkauf",
    }
    resp = c.post(base, body, content_type=JSON)
    assert resp.status_code == 201, resp.content
    assert resp.json()["vat_rate"] == "19"
    resp = c.post(base, {**body, "vat_rate": "7"}, content_type=JSON)
    assert resp.json()["vat_rate"] == "7"
    resp = c.post(base, {**body, "vat_rate": ""}, content_type=JSON)
    assert resp.json()["vat_rate"] == ""


def test_datev_schluessel(club):
    k = Kasse(club)
    income = k.buchen("business", "119.00", "19")
    reduced = k.buchen("purpose", "107.00", "7")
    expense = k.buchen("business", "119.00", "19", kind="expense")
    partly = k.buchen("business", "119.00", "19", kind="expense", share=50)
    ideal = k.buchen("ideal", "119.00", "19", kind="expense")
    storno = k.buchen("business", "119.00", "", kind="expense", cancels=income)
    assert datev.bu_key(income, True) == "3"
    assert datev.bu_key(reduced, True) == "2"
    assert datev.bu_key(expense, True) == "9"
    assert datev.bu_key(partly, True) == ""
    assert datev.bu_key(ideal, True) == ""
    assert datev.bu_key(storno, True) == "3"
    assert datev.bu_key(income, False) == ""


def test_ohne_modul_nicht_gefunden(c, club):
    club.enabled_modules = ["finance", "members"]
    club.save()
    assert c.get(f"/api/orgs/{club.pk}/finance/vat/").status_code == 404
