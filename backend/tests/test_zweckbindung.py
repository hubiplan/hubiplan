"""Zweckgebundene Spenden (Konzept vereinskasse-steuern, S5); erfundene Daten."""

import datetime
from decimal import Decimal

import pytest

from core.tenancy import tenant_context
from finance import earmarks
from finance.models import Account, Booking, Category, Donation, DonationSettings, Earmark

pytestmark = pytest.mark.django_db
JSON = "application/json"
D = datetime.date


@pytest.fixture
def club(orgs):
    club = orgs["a"]
    club.enabled_modules = ["finance", "members", "donations"]
    club.save()
    with tenant_context(club.pk):
        DonationSettings.objects.update_or_create(organization=club, defaults={"enabled": True})
    return club


@pytest.fixture
def kasse(club):
    with tenant_context(club.pk):
        account = Account.objects.create(
            organization=club, name="Girokonto", kind="bank", opening_date=D(2020, 1, 1)
        )
        cat = Category.objects.create(organization=club, name="Fahne", kind="expense")
    return account, cat


def ausgabe(club, account, cat, number, amount, earmark=None, **kw):
    with tenant_context(club.pk):
        return Booking.objects.create(
            organization=club,
            year=2025,
            number=number,
            date=D(2025, 6, number),
            kind=kw.pop("kind", "expense"),
            amount=Decimal(amount),
            account=account,
            category=cat,
            text="Fahne",
            earmark=earmark,
            **kw,
        )


def test_rest_und_zeitnahe_verwendung(club, kasse):
    account, cat = kasse
    with tenant_context(club.pk):
        fahne = Earmark.objects.create(organization=club, name="Neue Fahne")
        for amount in ("500", "300"):
            Donation.objects.create(
                organization=club,
                date=D(2022, 3, 1),
                amount=Decimal(amount),
                donor_name="Erika Musterfrau",
                earmark=fahne,
            )
    ausgabe(club, account, cat, 1, "200", fahne)
    storniert = ausgabe(club, account, cat, 2, "100", fahne)
    ausgabe(club, account, None, 3, "100", None, kind="income", cancels=storniert)
    row = earmarks.overview(club, today=D(2025, 7, 1))[0]
    assert row["received"] == Decimal("800")
    assert row["used"] == Decimal("200")
    assert row["rest"] == Decimal("600")
    assert row["overdue"] is True
    assert earmarks.overview(club, today=D(2024, 7, 1))[0]["overdue"] is False


def test_api(api, board_a, club, kasse):
    account, cat = kasse
    c = api(board_a)
    fin = f"/api/orgs/{club.pk}/finance"
    resp = c.post(f"{fin}/earmarks/", {"name": "Neue Fahne"}, JSON)
    assert resp.status_code == 201, resp.content
    pk = resp.json()["id"]
    assert c.post(f"{fin}/earmarks/", {"name": "neue  fahne"}, JSON).status_code == 400
    d = c.post(
        f"{fin}/donations/",
        {"date": "2025-01-15", "amount": "150.00", "donor_name": "Max Muster", "earmark": pk},
        JSON,
    )
    assert d.status_code == 201, d.content
    assert d.json()["earmark_name"] == "Neue Fahne"
    b = ausgabe(club, account, cat, 1, "50")
    resp = c.patch(f"{fin}/bookings/{b.pk}/", {"earmark": pk}, JSON)
    assert resp.status_code == 200, resp.content
    listing = c.get(f"{fin}/earmarks/").json()
    assert listing[0]["rest"] == "100.00"
    # Zugeordnet: nicht löschen, nur archivieren
    assert c.delete(f"{fin}/earmarks/{pk}/").status_code == 400
    # Einnahmen lassen sich nicht zweckbinden
    e = ausgabe(club, account, None, 2, "20", kind="income")
    assert c.patch(f"{fin}/bookings/{e.pk}/", {"earmark": pk}, JSON).status_code == 400
