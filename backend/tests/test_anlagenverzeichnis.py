"""Anlagenverzeichnis mit Abschreibung (Konzept vereinskasse-steuern, Abschnitt 5);
erfundene Daten."""

import datetime
from decimal import Decimal

import pytest

from core.tenancy import tenant_context
from finance import assets, tax
from finance.models import Account, Booking, Category, FixedAsset

pytestmark = pytest.mark.django_db
JSON = "application/json"
D = datetime.date


@pytest.fixture
def club(orgs):
    club = orgs["a"]
    club.enabled_modules = ["finance", "members", "tax"]
    club.tax_areas_enabled = True
    club.save()
    return club


@pytest.fixture
def c(api, board_a):
    return api(board_a)


@pytest.fixture
def fin(club):
    return f"/api/orgs/{club.pk}/finance"


def anlage(club, **kw):
    data = {
        "name": "Festzelt",
        "acquired_on": D(2025, 4, 10),
        "cost": Decimal("12000"),
        "method": FixedAsset.Method.LINEAR,
        "useful_life": 10,
        "tax_area": "business",
    }
    data.update(kw)
    with tenant_context(club.pk):
        return FixedAsset.objects.create(organization=club, **data)


def test_linear_monatsgenau(club):
    zelt = anlage(club)
    # 2025: April bis Dezember = 9 von 120 Monaten
    v = assets.year_values(zelt, club, 2025)
    assert v["depreciation"] == Decimal("900.00")
    assert v["book_end"] == Decimal("11100.00")
    v = assets.year_values(zelt, club, 2026)
    assert v["depreciation"] == Decimal("1200.00")
    assert v["book_start"] == Decimal("11100.00")
    # Im letzten Jahr nur noch der Rest
    assert assets.year_values(zelt, club, 2035)["depreciation"] == Decimal("300.00")
    assert assets.year_values(zelt, club, 2036)["depreciation"] == Decimal("0.00")


def test_abgang_mit_restwert(club):
    zelt = anlage(club, disposal="sold", disposed_on=D(2026, 6, 30))
    v = assets.year_values(zelt, club, 2026)
    # Januar bis Juni 2026
    assert v["depreciation"] == Decimal("600.00")
    assert v["residual"] == Decimal("10500.00")
    assert v["book_end"] == Decimal("0")
    assert assets.year_values(zelt, club, 2027)["depreciation"] == Decimal("0.00")


def test_gwg_und_sammelposten(club):
    beamer = anlage(club, name="Beamer", cost=Decimal("700"), method="gwg")
    assert assets.year_values(beamer, club, 2025)["depreciation"] == Decimal("700")
    assert assets.year_values(beamer, club, 2026)["depreciation"] == Decimal("0")
    pool = anlage(club, name="Biertischgarnituren", cost=Decimal("900"), method="pool")
    values = [assets.year_values(pool, club, y)["depreciation"] for y in range(2025, 2031)]
    assert values == [Decimal("180.00")] * 5 + [Decimal("0.00")]


def test_grenzen_der_methoden(c, fin, club):
    resp = c.post(
        f"{fin}/assets/",
        {
            "name": "Kühlanhänger",
            "acquired_on": "2025-05-01",
            "cost": "4500.00",
            "method": "gwg",
            "tax_area": "business",
        },
        content_type=JSON,
    )
    assert resp.status_code == 400
    assert "method" in resp.json()
    resp = c.post(
        f"{fin}/assets/",
        {
            "name": "Kühlanhänger",
            "acquired_on": "2025-05-01",
            "cost": "4500.00",
            "method": "linear",
            "useful_life": 8,
            "tax_area": "business",
        },
        content_type=JSON,
    )
    assert resp.status_code == 201, resp.json()


def test_verzeichnis_mit_jahreswerten_und_excel(c, fin, club):
    anlage(club)
    data = c.get(f"{fin}/assets/", {"jahr": 2026}).json()
    assert data["assets"][0]["values"]["depreciation"] == "1200.00"
    assert data["totals"]["book_end"] == "9900.00"
    xlsx = c.get(f"{fin}/assets/", {"jahr": 2026, "als": "xlsx"})
    assert xlsx.status_code == 200
    assert xlsx.content.startswith(b"PK")


def test_steuerauswertung_ersetzt_anschaffung_durch_afa(c, fin, club):
    with tenant_context(club.pk):
        account = Account.objects.create(
            organization=club, name="Girokonto", kind="bank", opening_date=D(2020, 1, 1)
        )
        festbetrieb = Category.objects.create(organization=club, name="Fest", tax_area="business")
        Booking.objects.create(
            organization=club,
            year=2026,
            number=1,
            date=D(2026, 5, 1),
            kind="income",
            amount=Decimal("10000"),
            account=account,
            category=festbetrieb,
            text="Getränkeverkauf",
        )
        kauf = Booking.objects.create(
            organization=club,
            year=2026,
            number=2,
            date=D(2026, 4, 10),
            kind="expense",
            amount=Decimal("12000"),
            account=account,
            category=festbetrieb,
            text="Festzelt",
        )
    anlage(club, acquired_on=D(2026, 4, 10), booking=kauf)
    data = tax.report(club, 2026, today=D(2026, 11, 6))
    # Kassenergebnis -2.000 €, nach AfA: 10.000 - 900 = 9.100 €
    assert data["business_result"] == Decimal("-2000")
    assert data["business_result_after"] == Decimal("9100.00")
    area = data["depreciation"]["areas"][0]
    assert area["purchases"] == Decimal("12000") and area["depreciation"] == Decimal("900.00")
    assert "loss" not in {w["kind"] for w in data["warnings"]}
    # Die API liefert dasselbe
    api_data = c.get(f"{fin}/tax/", {"jahr": 2026}).json()
    assert api_data["business_result_after"] == "9100.00"


def test_ohne_anlagen_keine_korrektur(club):
    data = tax.report(club, 2026, today=D(2026, 11, 6))
    assert data["depreciation"] is None
    assert data["business_result_after"] is None


def test_nur_mit_modul(c, fin, club):
    club.enabled_modules = ["finance", "members"]
    club.save()
    assert c.get(f"{fin}/assets/").status_code == 404


def test_ohne_kasse_kein_zugriff(api, board_c, club):
    assert api(board_c).get(f"/api/orgs/{club.pk}/finance/assets/").status_code in (403, 404)
