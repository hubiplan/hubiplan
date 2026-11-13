"""Haushaltsplan: Plan und Ist je Kategorie und Untereinheit; erfundene Daten."""

import datetime
from decimal import Decimal

import pytest

from core.tenancy import tenant_context
from finance import budget
from finance.models import Account, Booking, Budget, Category, Project
from organizations.models import Department

pytestmark = pytest.mark.django_db
D = datetime.date


@pytest.fixture
def club(orgs):
    club = orgs["a"]
    club.enabled_modules = ["finance", "members"]
    club.save()
    return club


@pytest.fixture
def heute(monkeypatch):
    day = {"value": D(2026, 7, 1)}
    monkeypatch.setattr(budget, "_today", lambda: day["value"])
    return day


@pytest.fixture
def kasse(club):
    with tenant_context(club.pk):
        account = Account.objects.create(
            organization=club, name="Girokonto", kind="bank", opening_date=D(2020, 1, 1)
        )
        cats = {
            "beitraege": Category.objects.create(organization=club, name="Beiträge", kind="income"),
            "fest": Category.objects.create(organization=club, name="Schützenfest"),
            "musik": Category.objects.create(organization=club, name="Musik", kind="expense"),
        }
        zug = Department.objects.create(name="1. Zug", parent=club, organization=club)
    return account, cats, zug


def buchen(club, account, cat, day, amount, kind, department=None, cancels=None):
    with tenant_context(club.pk):
        return Booking.objects.create(
            organization=club,
            year=day.year,
            number=Booking.objects.filter(organization=club, year=day.year).count() + 1,
            date=day,
            kind=kind,
            amount=Decimal(amount),
            account=account,
            category=cat,
            department=department,
            text="Muster",
            cancels=cancels,
        )


def plan(club, year, lines, user=None):
    with tenant_context(club.pk):
        return budget.save(club, year, {"lines": lines}, user)[0]


def test_plan_ist_und_zuordnung(club, kasse, heute):
    account, cats, zug = kasse
    buchen(club, account, cats["beitraege"], D(2026, 2, 1), "5000", "income")
    buchen(club, account, cats["fest"], D(2026, 6, 1), "800", "expense")
    buchen(club, account, cats["fest"], D(2026, 6, 2), "300", "expense", department=zug)
    buchen(club, account, cats["musik"], D(2026, 6, 3), "1200", "expense")
    plan(
        club,
        2026,
        [
            {"kind": "income", "category": cats["beitraege"].pk, "amount": "6000"},
            {"kind": "expense", "category": cats["fest"].pk, "amount": "1000"},
            {"kind": "expense", "category": cats["fest"].pk, "department": zug.pk, "amount": "250"},
        ],
    )
    with tenant_context(club.pk):
        data = budget.report(club, 2026)
    assert data["phase"] == "current"
    by = {(ln["kind"], ln["category"], ln["department"]): ln for ln in data["lines"]}
    assert by[("income", cats["beitraege"].pk, None)]["actual"] == Decimal("5000")
    # Zug hat eine eigene Zeile, die allgemeine Zeile zählt nur den Rest
    assert by[("expense", cats["fest"].pk, zug.pk)]["actual"] == Decimal("300")
    assert by[("expense", cats["fest"].pk, None)]["actual"] == Decimal("800")
    # Musik ist nicht geplant
    assert [(u["category"], u["actual"]) for u in data["unplanned"]] == [
        (cats["musik"].pk, Decimal("1200"))
    ]
    t = data["totals"]
    assert t["income"]["plan"] == Decimal("6000")
    assert t["expense"]["plan"] == Decimal("1250")
    assert t["expense"]["actual"] == Decimal("2300")
    assert t["result"]["plan"] == Decimal("4750")


def test_storno_mindert_die_seite(club, kasse, heute):
    account, cats, _zug = kasse
    original = buchen(club, account, cats["musik"], D(2026, 3, 1), "400", "expense")
    buchen(club, account, cats["musik"], D(2026, 3, 2), "400", "income", cancels=original)
    plan(club, 2026, [{"kind": "expense", "category": cats["musik"].pk, "amount": "500"}])
    with tenant_context(club.pk):
        data = budget.report(club, 2026)
    assert data["lines"][0]["actual"] == Decimal("0")
    assert data["unplanned"] == []


def test_hochrechnung_nach_vorjahr(club, kasse, heute):
    account, cats, _zug = kasse
    # Vorjahr: 200 € bis Juni, 3.000 € beim Fest im August
    buchen(club, account, cats["fest"], D(2025, 3, 1), "200", "income")
    buchen(club, account, cats["fest"], D(2025, 8, 20), "3000", "income")
    buchen(club, account, cats["fest"], D(2026, 3, 1), "250", "income")
    # Beiträge ohne Vorjahr: Hochrechnung = Plan, solange das Ist darunter liegt
    buchen(club, account, cats["beitraege"], D(2026, 2, 1), "1000", "income")
    plan(
        club,
        2026,
        [
            {"kind": "income", "category": cats["fest"].pk, "amount": "3000"},
            {"kind": "income", "category": cats["beitraege"].pk, "amount": "4000"},
        ],
    )
    with tenant_context(club.pk):
        data = budget.report(club, 2026)
    by = {ln["category"]: ln for ln in data["lines"]}
    assert by[cats["fest"].pk]["forecast"] == Decimal("3250")
    assert by[cats["fest"].pk]["previous_actual"] == Decimal("3200")
    assert by[cats["beitraege"].pk]["forecast"] == Decimal("4000")
    assert data["elapsed_percent"] == 50


def test_kuenftiges_jahr_ohne_ist(club, kasse, heute):
    account, cats, _zug = kasse
    plan(club, 2027, [{"kind": "income", "category": cats["beitraege"].pk, "amount": "100"}])
    with tenant_context(club.pk):
        data = budget.report(club, 2027)
    assert data["phase"] == "future"
    assert data["lines"][0]["actual"] is None
    assert data["totals"]["income"]["actual"] is None
    assert 2027 in [y["year"] for y in data["years"]]


def test_vorjahr_uebernehmen(club, kasse, heute):
    account, cats, zug = kasse
    buchen(club, account, cats["fest"], D(2025, 8, 20), "2999.60", "income", department=zug)
    buchen(club, account, cats["musik"], D(2025, 8, 21), "700", "expense")
    with tenant_context(club.pk):
        plan_ = budget.copy_previous(club, 2026, "actual", None)[0]
        lines = {(ln.kind, ln.category_id, ln.department_id): ln.amount for ln in plan_.lines.all()}
    assert lines == {
        ("income", cats["fest"].pk, zug.pk): Decimal("3000.00"),
        ("expense", cats["musik"].pk, None): Decimal("700.00"),
    }
    with tenant_context(club.pk), pytest.raises(budget.BudgetError):
        budget.copy_previous(club, 2026, "plan", None)
    with tenant_context(club.pk):
        budget.copy_previous(club, 2027, "plan", None)
        assert Budget.objects.get(organization=club, year=2027).lines.count() == 2


def test_beschlossen_ist_gesperrt(club, kasse, heute):
    _account, cats, _zug = kasse
    line = [{"kind": "income", "category": cats["beitraege"].pk, "amount": "100"}]
    plan(club, 2026, line)
    with tenant_context(club.pk):
        budget.set_status(club, 2026, {"status": "adopted", "adopted_on": "2026-03-01"}, None)
        with pytest.raises(budget.BudgetError) as exc:
            budget.save(club, 2026, {"lines": line}, None)
        assert "status" in exc.value.errors
        with pytest.raises(budget.BudgetError):
            budget.delete(club, 2026)
        budget.set_status(club, 2026, {"status": "draft"}, None)
        budget.save(club, 2026, {"lines": line}, None)


def test_pruefungen(club, kasse, heute, orgs):
    _account, cats, _zug = kasse
    with tenant_context(orgs["b"].pk):
        fremd = Category.objects.create(organization=orgs["b"], name="Fremd")
    bad = [
        [{"kind": "expense", "category": cats["beitraege"].pk, "amount": "1"}],  # nur Einnahmen
        [{"kind": "income", "category": fremd.pk, "amount": "1"}],
        [{"kind": "income", "category": cats["fest"].pk, "amount": "-5"}],
        [{"kind": "income", "category": cats["fest"].pk, "amount": "1"}] * 2,
        [{"kind": "x", "category": cats["fest"].pk, "amount": "1"}],
    ]
    for lines in bad:
        with tenant_context(club.pk), pytest.raises(budget.BudgetError):
            budget.save(club, 2026, {"lines": lines}, None)
    with tenant_context(club.pk):
        first = budget.save(club, 2026, {"lines": []}, None)[0]
        with pytest.raises(budget.BudgetError) as exc:
            budget.save(club, 2026, {"lines": [], "version": first.version + 5}, None)
    assert "version" in exc.value.errors


def test_api_rechte_pdf_excel(api, board_a, board_b, club, kasse, heute):
    _account, cats, _zug = kasse
    c = api(board_a)
    url = f"/api/orgs/{club.pk}/finance/budget/?jahr=2026"
    resp = c.put(
        url,
        {"lines": [{"kind": "income", "category": cats["beitraege"].pk, "amount": "12,50"}]},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["lines"][0]["amount"] == "12.50"
    assert body["budget"]["status"] == "draft"
    resp = c.post(
        f"/api/orgs/{club.pk}/finance/budget/status/?jahr=2026",
        {"status": "adopted", "adopted_on": "2026-03-01", "adopted_by": "Mitgliederversammlung"},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["budget"]["status"] == "adopted"
    pdf = c.get(url + "&als=pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    xlsx = c.get(url + "&als=xlsx")
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    # fremder Verein sieht nichts
    assert api(board_b).get(url).status_code in (403, 404)
    club.enabled_modules = ["members"]
    club.save()
    assert c.get(url).status_code == 404


def test_planwerte_an_veranstaltung(api, board_a, club, kasse):
    c = api(board_a)
    resp = c.post(
        f"/api/orgs/{club.pk}/finance/projects/",
        {"name": "Schützenfest", "starts_on": "2026-08-20", "plan_income": "5000"},
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content
    assert resp.json()["plan_income"] == "5000.00"
    with tenant_context(club.pk):
        project = Project.objects.get(pk=resp.json()["id"])
    from finance.projects import _evaluation

    with tenant_context(club.pk):
        assert _evaluation(project)["plan"]["result"] == Decimal("5000")
    bad = c.patch(
        f"/api/orgs/{club.pk}/finance/projects/{project.pk}/",
        {"plan_expense": "-1"},
        content_type="application/json",
    )
    assert bad.status_code == 400


def test_kategorie_mit_planzeile_nicht_loeschbar(club, kasse, heute):
    from django.db.models import ProtectedError

    _account, cats, _zug = kasse
    plan(club, 2026, [{"kind": "expense", "category": cats["musik"].pk, "amount": "1"}])
    with tenant_context(club.pk), pytest.raises(ProtectedError):
        cats["musik"].delete()
