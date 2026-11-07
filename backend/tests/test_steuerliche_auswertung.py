"""Steuerliche Auswertung (Konzept vereinskasse-steuern, S1): Freigrenze, Bereiche,
Stornos, Untereinheiten, Kleinunternehmer, Erklärungshinweis (erfundene Daten)."""

import datetime
from decimal import Decimal

import pytest
from django.db import connection

from core.rls import APP_ROLE
from core.tenancy import set_rls, tenant_context
from finance import tax
from finance.models import Account, Booking, Category, DonationSettings
from organizations.models import Department

pytestmark = pytest.mark.django_db
JSON = "application/json"


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


@pytest.fixture
def unit(c, club):
    unit = Department.objects.create(organization=club, name="Spielmannszug", founding_year=1980)
    resp = c.patch(
        f"/api/orgs/{club.pk}/departments/{unit.pk}/", {"own_workspace": True}, content_type=JSON
    )
    assert resp.status_code == 200, resp.json()
    unit.refresh_from_db()
    return unit


class Kasse:
    """Konto und Kategorien einer Einheit, Buchungen direkt im Modell."""

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

    def buchen(self, area, amount, kind="income", day=datetime.date(2026, 6, 1), cancels=None):
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
                cancels=cancels,
            )


def get(c, org, year=2026):
    resp = c.get(f"/api/orgs/{org.pk}/finance/tax/?jahr={year}")
    assert resp.status_code == 200, resp.content
    return resp.json()


def test_grenzen_je_jahr():
    assert tax.free_limit(2019) == Decimal("35000")
    assert tax.free_limit(2025) == Decimal("45000")
    assert tax.free_limit(2026) == Decimal("50000")
    assert tax.small_limits(2026) == (Decimal("25000"), Decimal("100000"))
    assert tax.small_limits(2024) == (Decimal("22000"), Decimal("50000"))


def test_ampel_und_bereiche(c, club):
    k = Kasse(club)
    k.buchen("business", "41000")
    k.buchen("business", "9000", kind="expense")
    k.buchen("ideal", "5000")
    data = get(c, club)
    fl = data["free_limit"]
    assert fl == {"limit": "50000.00", "income": "41000.00", "status": "warn", "percent": 82}
    assert data["business_result"] == "32000.00"
    areas = {a["area"]: a for a in data["areas"]}
    assert areas["ideal"]["income"] == "5000.00"
    assert areas["business"]["result"] == "32000.00"
    k.buchen("business", "9500")
    assert get(c, club)["free_limit"]["status"] == "over"
    # 2025 galt noch 45.000 €
    k.buchen("business", "44000", day=datetime.date(2025, 5, 1))
    old = get(c, club, 2025)["free_limit"]
    assert old["limit"] == "45000.00" and old["status"] == "warn"


def test_storno_mindert_die_einnahme(c, club):
    k = Kasse(club)
    original = k.buchen("business", "1000")
    k.buchen("business", "1000", kind="expense", cancels=original)
    data = get(c, club)
    assert data["free_limit"]["income"] == "0.00"
    assert data["areas"] == []


def test_verlust_und_fehlender_bereich(c, club):
    k = Kasse(club)
    k.buchen("business", "500")
    k.buchen("business", "800", kind="expense")
    k.buchen("", "120")
    data = get(c, club)
    kinds = {w["kind"] for w in data["warnings"]}
    assert kinds == {"loss", "unassigned"}
    assert "§ 55" in next(w["text"] for w in data["warnings"] if w["kind"] == "loss")


def test_untereinheit_zaehlt_beim_verein_mit(c, club, unit):
    Kasse(club).buchen("business", "30000")
    Kasse(unit).buchen("business", "25000")
    data = get(c, club)
    assert data["free_limit"]["income"] == "55000.00"
    assert data["free_limit"]["status"] == "over"
    assert [(u["name"], u["business_income"]) for u in data["units"]] == [
        ("Spielmannszug", "25000.00")
    ]
    # Steuerlich selbständig: zählt nicht mehr beim Verein
    resp = c.patch(
        f"/api/orgs/{club.pk}/departments/{unit.pk}/", {"tax_independent": True}, content_type=JSON
    )
    assert resp.status_code == 200, resp.json()
    assert resp.json()["tax_independent"] is True
    data = get(c, club)
    assert data["free_limit"]["income"] == "30000.00"
    assert data["units"] == []


def test_untereinheit_sieht_nur_eigene_zahlen(c, club, unit):
    Kasse(club).buchen("business", "30000")
    Kasse(unit).buchen("business", "25000")
    unit.tax_areas_enabled = True
    unit.save()
    data = tax.report(unit, 2026, today=datetime.date(2026, 11, 6))
    assert data["root"]["is_self"] is False
    assert data["root"]["id"] == club.pk
    assert data["free_limit"]["income"] == Decimal("25000")
    assert data["small_business"] is None
    assert data["declaration"] is None


@pytest.mark.skipif(connection.vendor != "postgresql", reason="RLS nur mit PostgreSQL")
def test_summen_der_untereinheit_unter_rls(c, club, unit):
    Kasse(club).buchen("business", "1000")
    Kasse(unit).buchen("business", "2000")
    with connection.cursor() as cursor:
        cursor.execute(f"SET ROLE {APP_ROLE}")
    try:
        data = get(c, club)
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
        set_rls(None, None, False)
    assert data["free_limit"]["income"] == "3000.00"


def test_kleinunternehmer(c, club):
    k = Kasse(club)
    k.buchen("purpose", "20000", day=datetime.date(2025, 3, 1))
    k.buchen("business", "7000", day=datetime.date(2025, 4, 1))
    k.buchen("ideal", "50000", day=datetime.date(2025, 4, 1))  # Beiträge zählen nicht
    k.buchen("business", "10000")
    sb = get(c, club)["small_business"]
    assert sb["previous"] == "27000.00"
    assert sb["current"] == "10000.00"
    assert sb["status"] == "over"


def test_kleinunternehmer_entfaellt_mit_umsatzsteuer(c, club):
    from billing.models import BillingSettings

    with tenant_context(club.pk):
        BillingSettings.objects.update_or_create(organization=club, defaults={"vat_enabled": True})
    assert get(c, club)["small_business"] is None


def test_erklaerungshinweis(club):
    with tenant_context(club.pk):
        cfg = DonationSettings.objects.create(
            organization=club, enabled=True, assessment_period="2021 bis 2023"
        )
    hint = tax.declaration_hint(club, today=datetime.date(2026, 11, 6))
    assert hint["next_from"] == 2024 and hint["next_to"] == 2026 and hint["due"] is False
    cfg.assessment_period = "2020 bis 2022"
    cfg.save()
    hint = tax.declaration_hint(club, today=datetime.date(2026, 11, 6))
    assert hint["due"] is True
    cfg.assessment_period = ""
    cfg.save()
    assert tax.declaration_hint(club)["known"] is False


def test_pdf_und_excel(c, club, unit):
    Kasse(club).buchen("business", "1234.56")
    Kasse(unit).buchen("purpose", "99")
    base = f"/api/orgs/{club.pk}/finance/tax/?jahr=2026"
    pdf = c.get(f"{base}&als=pdf")
    assert pdf.status_code == 200
    assert pdf["Content-Type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    xlsx = c.get(f"{base}&als=xlsx")
    assert xlsx.status_code == 200
    assert xlsx.content.startswith(b"PK")


def test_ohne_kasse_kein_zugriff(api, board_c, club):
    assert api(board_c).get(f"/api/orgs/{club.pk}/finance/tax/").status_code in (403, 404)
