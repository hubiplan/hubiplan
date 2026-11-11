"""Geschäftspartner in der Kasse (Konzept geschaeftspartner.md, P2): Verweis an Buchungen,
Vorschläge, Bankzeilen per IBAN, Umsätze, Künstlersozialabgabe, Bestand übernehmen."""
# ruff: noqa: F811  (Fixtures als Parameter)

from decimal import Decimal

import pytest

from billing.models import BusinessPartner
from core.tenancy import tenant_context
from finance import artist_fees
from finance.bank_import import partners_by_iban
from finance.models import Booking

from .test_m9_billing import JSON, base, c, club, setup, zug  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def fin(club):
    return f"/api/orgs/{club.pk}/finance"


@pytest.fixture
def partners(club):
    return f"/api/orgs/{club.pk}/billing/partners/"


@pytest.fixture
def expense_cat(c, fin):
    return c.post(
        f"{fin}/categories/", {"name": "Getränkeeinkauf", "kind": "expense"}, content_type=JSON
    ).json()["id"]


def partner(c, partners, name="Getränke Beispiel GmbH", **extra):
    response = c.post(partners, {"details": {"name": name}, **extra}, content_type=JSON)
    assert response.status_code == 201, response.content
    return response.json()


def book(c, fin, setup, category, **extra):
    body = {
        "date": "2026-03-01",
        "kind": "expense",
        "amount": "120",
        "account": setup["bank"],
        "category": category,
        "text": "Fassbier",
        **extra,
    }
    response = c.post(f"{fin}/bookings/", body, content_type=JSON)
    assert response.status_code == 201, response.content
    return response.json()


def test_buchung_mit_partner_uebernimmt_namen(c, fin, setup, partners, expense_cat):
    p = partner(c, partners, roles=["supplier"])
    b = book(c, fin, setup, expense_cat, partner=p["id"])
    assert b["partner"] == p["id"]
    assert b["counterparty"] == "Getränke Beispiel GmbH"
    assert b["partner_name"] == "Getränke Beispiel GmbH"
    # eigener Freitext bleibt
    own = book(c, fin, setup, expense_cat, partner=p["id"], counterparty="Getränke B.")
    assert own["counterparty"] == "Getränke B."


def test_partner_eines_anderen_vereins_abgelehnt(c, fin, setup, orgs, expense_cat):
    with tenant_context(orgs["b"].pk):
        foreign = BusinessPartner.objects.create(
            organization=orgs["b"], name="Fremd", details={"name": "Fremd"}
        )
    body = {
        "date": "2026-03-01",
        "kind": "expense",
        "amount": "10",
        "account": setup["bank"],
        "category": expense_cat,
        "text": "x",
        "partner": foreign.pk,
    }
    assert c.post(f"{fin}/bookings/", body, content_type=JSON).status_code == 400


def test_vorschlaege_nennen_partner_zuerst(c, fin, setup, partners, expense_cat):
    book(c, fin, setup, expense_cat, counterparty="Bäckerei Muster")
    p = partner(c, partners, name="Zeltverleih Beispiel")
    c.patch(f"{partners}{p['id']}/", {"default_category": expense_cat}, content_type=JSON)
    rows = c.get(f"{fin}/bookings/counterparties/?art=expense").json()
    assert rows[0] == {
        "name": "Zeltverleih Beispiel",
        "count": 0,
        "partner": p["id"],
        "category": expense_cat,
    }
    assert {"name": "Bäckerei Muster", "count": 1} in rows


def test_storno_behaelt_partner(c, fin, setup, partners, expense_cat, club):
    p = partner(c, partners)
    b = book(c, fin, setup, expense_cat, partner=p["id"])
    response = c.post(
        f"{fin}/bookings/{b['id']}/storno/", {"reason": "Doppelt gebucht"}, content_type=JSON
    )
    assert response.status_code in (200, 201), response.content
    with tenant_context(club.pk):
        assert Booking.objects.filter(partner_id=p["id"]).count() == 2


def test_umsaetze_ohne_stornos(c, fin, setup, partners, expense_cat, club):
    p = partner(c, partners)
    book(c, fin, setup, expense_cat, partner=p["id"])
    book(c, fin, setup, expense_cat, partner=p["id"], amount="30", date="2026-04-01")
    data = c.get(f"{partners}{p['id']}/turnover/").json()
    assert data["years"] == [{"year": 2026, "income": "0.00", "expense": "150.00", "count": 2}]
    assert len(data["recent"]) == 2


def test_bestand_uebernehmen(c, fin, setup, partners, expense_cat, club):
    for _ in range(2):
        book(c, fin, setup, expense_cat, counterparty="Druckerei  Muster")
    book(c, fin, setup, expense_cat, counterparty="Einmalig GmbH")
    rows = c.get(f"{partners}suggestions/").json()
    assert rows == [{"name": "Druckerei Muster", "count": 2}]
    response = c.post(f"{partners}suggestions/", {"name": "Druckerei Muster"}, content_type=JSON)
    assert response.status_code == 201, response.content
    assert response.json()["linked"] == 2
    assert c.get(f"{partners}suggestions/").json() == []
    again = c.post(f"{partners}suggestions/", {"name": "Druckerei Muster"}, content_type=JSON)
    assert again.status_code == 400


def test_kuenstlerkennzeichen_zaehlt_fuer_ksk(c, fin, setup, partners, expense_cat, club):
    p = partner(c, partners, name="DJ Beispiel", roles=["artist"])
    assert c.get(f"{partners}{p['id']}/").json()["artist"] is True
    book(c, fin, setup, expense_cat, partner=p["id"], amount="300")
    with tenant_context(club.pk):
        rows = list(artist_fees.bookings(club, 2026))
    assert [b.amount for b in rows] == [Decimal("300.00")]


def test_bankzeile_findet_partner_ueber_iban(c, partners, club):
    p = partner(c, partners, bank={"iban": "DE02 1203 0000 0000 2020 51"})
    with tenant_context(club.pk):
        found = partners_by_iban(club)
    assert found["DE02120300000000202051"].pk == p["id"]


def test_zusammenfuehren_nimmt_buchungen_mit(c, fin, setup, partners, expense_cat, club):
    keep = partner(c, partners)
    other = partner(c, partners, name="Getränke Beispiel")
    book(c, fin, setup, expense_cat, partner=other["id"])
    assert c.delete(f"{partners}{other['id']}/").status_code == 400
    response = c.post(f"{partners}{keep['id']}/merge/", {"other": other["id"]}, content_type=JSON)
    assert response.status_code == 200, response.content
    with tenant_context(club.pk):
        assert Booking.objects.filter(partner_id=keep["id"]).count() == 1
