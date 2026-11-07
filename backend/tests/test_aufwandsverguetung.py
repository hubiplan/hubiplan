"""Aufwandsvergütungen (Konzept vereinskasse-steuern, S3): Übungsleiterfreibetrag und
Ehrenamtspauschale je Person und Kalenderjahr (erfundene Daten)."""

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from access.models import Role, RoleAssignment
from core.tenancy import tenant_context
from finance import allowances
from finance.models import Account, Category

from .factories import make_member

pytestmark = pytest.mark.django_db
JSON = "application/json"


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
            organization=club, name="Kasse", kind="cash", opening_date=datetime.date(2020, 1, 1)
        )
        cat = Category.objects.create(organization=club, name="Aufwandsentschädigungen")
    return account, cat


@pytest.fixture
def trainerin(club):
    return make_member(club, "Erika", "Musterfrau")


def zahlen(c, fin, kasse, amount, allowance="trainer", membership=None, counterparty=""):
    account, cat = kasse
    resp = c.post(
        f"{fin}/bookings/",
        {
            "date": timezone.localdate().isoformat(),
            "kind": "expense",
            "amount": amount,
            "account": account.pk,
            "category": cat.pk,
            "text": "Aufwandsentschädigung",
            "counterparty": counterparty,
            "membership": membership.pk if membership else None,
            "allowance": allowance,
        },
        content_type=JSON,
    )
    return resp


def get(c, fin, **params):
    year = timezone.localdate().year
    resp = c.get(f"{fin}/allowances/", {"jahr": year, **params})
    assert resp.status_code == 200, resp.content
    return resp.json()


def test_grenzen_je_jahr():
    assert allowances.limits(2026) == {"trainer": Decimal("3300"), "volunteer": Decimal("960")}
    assert allowances.limits(2025) == {"trainer": Decimal("3000"), "volunteer": Decimal("840")}
    assert allowances.limits(2020) == {"trainer": Decimal("2400"), "volunteer": Decimal("720")}


def test_summe_je_person_und_ampel(c, fin, kasse, trainerin):
    limit = allowances.limits(timezone.localdate().year)["trainer"]
    first = (limit * Decimal("0.5")).quantize(Decimal("0.01"))
    assert zahlen(c, fin, kasse, str(first), membership=trainerin).status_code == 201
    assert zahlen(c, fin, kasse, "120.00", "volunteer", counterparty="Max Platzwart").status_code
    data = get(c, fin)
    people = {p["name"]: p for p in data["people"]}
    erika = people["Erika Musterfrau"]
    assert erika["membership"] == trainerin.pk
    assert erika["kinds"][0]["kind"] == "trainer"
    assert erika["kinds"][0]["status"] == "ok"
    assert people["Max Platzwart"]["kinds"][0]["kind"] == "volunteer"
    # Zweite Zahlung über die Grenze
    rest = (limit - first + Decimal("1")).quantize(Decimal("0.01"))
    assert zahlen(c, fin, kasse, str(rest), membership=trainerin).status_code == 201
    data = get(c, fin)
    erika = next(p for p in data["people"] if p["membership"] == trainerin.pk)
    assert erika["kinds"][0]["status"] == "over"
    assert Decimal(erika["kinds"][0]["total"]) == limit + 1
    assert len(erika["bookings"]) == 2
    assert {w["kind"] for w in data["warnings"]} == {"over"}


def test_storno_zaehlt_nicht(c, fin, kasse, trainerin):
    booking = zahlen(c, fin, kasse, "500.00", membership=trainerin).json()
    resp = c.post(f"{fin}/bookings/{booking['id']}/storno/", {"reason": "Irrtum"}, JSON)
    assert resp.status_code in (200, 201), resp.json()
    assert get(c, fin)["people"] == []


def test_nur_ausgaben_mit_person(c, fin, kasse, club):
    resp = zahlen(c, fin, kasse, "50.00")
    assert resp.status_code == 400
    assert "allowance" in resp.json()
    account, cat = kasse
    resp = c.post(
        f"{fin}/bookings/",
        {
            "date": timezone.localdate().isoformat(),
            "kind": "income",
            "amount": "50.00",
            "account": account.pk,
            "category": cat.pk,
            "text": "Erstattung",
            "counterparty": "Erika Musterfrau",
            "allowance": "trainer",
        },
        content_type=JSON,
    )
    assert resp.status_code == 400
    assert "allowance" in resp.json()


def test_ohne_modul_nicht_moeglich(c, fin, kasse, club):
    club.enabled_modules = ["finance", "members"]
    club.save()
    resp = zahlen(c, fin, kasse, "50.00", counterparty="Max Platzwart")
    assert resp.status_code == 400
    assert c.get(f"{fin}/allowances/").status_code == 404


def test_vorstand_ohne_satzungsregel(c, fin, kasse, club, trainerin):
    with tenant_context(club.pk):
        role = Role.objects.create(organization=club, name="Kassiererin", is_board=True)
        RoleAssignment.objects.create(
            organization=club,
            role=role,
            person=trainerin.person,
            valid_from=datetime.date(2020, 1, 1),
        )
    assert zahlen(c, fin, kasse, "300.00", "volunteer", membership=trainerin).status_code == 201
    data = get(c, fin)
    assert data["people"][0]["board"] is True
    assert data["people"][0]["board_warning"] is True
    assert "§ 27 Abs. 3 BGB" in data["warnings"][0]["text"]
    resp = c.patch(f"{fin}/settings/", {"board_pay_allowed": True}, JSON)
    assert resp.status_code == 200 and resp.json()["board_pay_allowed"] is True
    data = get(c, fin)
    assert data["people"][0]["board_warning"] is False
    assert data["warnings"] == []


def test_erklaerung_als_pdf(c, fin, kasse, trainerin):
    zahlen(c, fin, kasse, "250.00", membership=trainerin)
    zahlen(c, fin, kasse, "80.00", "volunteer", membership=trainerin)
    key = get(c, fin)["people"][0]["key"]
    pdf = c.get(f"{fin}/allowances/", {"als": "pdf", "person": key})
    assert pdf.status_code == 200
    assert pdf["Content-Type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert c.get(f"{fin}/allowances/", {"als": "pdf", "person": "x"}).status_code == 404


def test_verguetung_nachtragen(c, fin, kasse, trainerin):
    booking = zahlen(c, fin, kasse, "90.00", allowance="", membership=trainerin).json()
    resp = c.patch(f"{fin}/bookings/{booking['id']}/", {"allowance": "trainer"}, JSON)
    assert resp.status_code == 200, resp.json()
    assert resp.json()["allowance"] == "trainer"


def test_ohne_kasse_kein_zugriff(api, board_c, club):
    assert api(board_c).get(f"/api/orgs/{club.pk}/finance/allowances/").status_code in (403, 404)
