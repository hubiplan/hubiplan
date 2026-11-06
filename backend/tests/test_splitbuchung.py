"""Splitbuchung (Konzept vereinskasse-steuern, S1b): ein Zahlungsvorgang, mehrere
Kategorien (erfundene Daten)."""

import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.tenancy import tenant_context
from finance import bank_import, services
from finance.models import Account, BankLine, BankStatement, Booking, Category, Receipt

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture
def club(orgs):
    club = orgs["a"]
    club.enabled_modules = ["finance", "members"]
    club.tax_areas_enabled = True
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
            organization=club,
            name="Girokonto",
            kind="bank",
            opening_date=datetime.date(2020, 1, 1),
        )
        cats = {
            name: Category.objects.create(organization=club, name=name, tax_area=area)
            for name, area in (
                ("Getränke", "business"),
                ("Eintritt", "purpose"),
                ("Bandenwerbung", "business"),
                ("Beiträge", "ideal"),
            )
        }
    return account, cats


def buchung(c, fin, account, cat, amount="1000.00", kind="income"):
    resp = c.post(
        f"{fin}/bookings/",
        {
            "date": timezone.localdate().isoformat(),
            "kind": kind,
            "amount": amount,
            "account": account.pk,
            "category": cat.pk,
            "text": "Abrechnung Festwirt",
            "counterparty": "Festwirt Muster",
        },
        content_type=JSON,
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()


def teilen(c, fin, booking_id, parts):
    return c.post(f"{fin}/bookings/{booking_id}/split/", {"parts": parts}, content_type=JSON)


def test_aufteilen_legt_teile_an(c, fin, kasse):
    account, cats = kasse
    b = buchung(c, fin, account, cats["Getränke"])
    resp = teilen(
        c,
        fin,
        b["id"],
        [
            {"category": cats["Getränke"].pk, "amount": "600.00"},
            {"category": cats["Eintritt"].pk, "amount": "300.00", "text": "Eintritt Festzelt"},
            {"category": cats["Bandenwerbung"].pk, "amount": "100.00"},
        ],
    )
    assert resp.status_code == 201, resp.json()
    rows = resp.json()
    assert [r["amount"] for r in rows] == ["600.00", "300.00", "100.00"]
    assert rows[0]["id"] == b["id"] and rows[0]["split"]["is_lead"] is True
    assert {p["number"] for p in rows[0]["split"]["parts"]} == {
        rows[1]["display_number"],
        rows[2]["display_number"],
    }
    assert rows[1]["split"]["lead"]["id"] == b["id"]
    assert rows[1]["text"] == "Eintritt Festzelt"
    assert rows[2]["text"] == "Abrechnung Festwirt"
    assert rows[2]["counterparty"] == "Festwirt Muster"
    lead = Booking.objects.get(pk=b["id"])
    assert services.group_amount(lead) == Decimal("1000.00")
    # Auswertung je Bereich sieht die Teile
    tax = c.get(f"{fin}/tax/?jahr={lead.year}").json()
    areas = {a["area"]: a["income"] for a in tax["areas"]}
    assert areas == {"purpose": "300.00", "business": "700.00"}


def test_summe_muss_stimmen(c, fin, kasse):
    account, cats = kasse
    b = buchung(c, fin, account, cats["Getränke"])
    resp = teilen(
        c,
        fin,
        b["id"],
        [
            {"category": cats["Getränke"].pk, "amount": "600.00"},
            {"category": cats["Eintritt"].pk, "amount": "300.00"},
        ],
    )
    assert resp.status_code == 400
    assert "genau" in str(resp.json())
    assert Booking.objects.filter(organization_id=account.organization_id).count() == 1


def test_nur_einmal_und_nicht_bei_storno(c, fin, kasse):
    account, cats = kasse
    b = buchung(c, fin, account, cats["Getränke"])
    parts = [
        {"category": cats["Getränke"].pk, "amount": "500.00"},
        {"category": cats["Eintritt"].pk, "amount": "500.00"},
    ]
    assert teilen(c, fin, b["id"], parts).status_code == 201
    again = teilen(c, fin, b["id"], parts)
    assert again.status_code == 400 and "schon aufgeteilt" in str(again.json())
    other = buchung(c, fin, account, cats["Getränke"], amount="50.00")
    resp = c.post(
        f"{fin}/bookings/{other['id']}/storno/", {"reason": "Tippfehler"}, content_type=JSON
    )
    assert resp.status_code == 201
    parts = [
        {"category": cats["Getränke"].pk, "amount": "25.00"},
        {"category": cats["Eintritt"].pk, "amount": "25.00"},
    ]
    resp = teilen(c, fin, other["id"], parts)
    assert resp.status_code == 400 and "Storno" in str(resp.json())


def test_kategorie_muss_zur_art_passen(c, fin, kasse, club):
    account, cats = kasse
    with tenant_context(club.pk):
        only_expense = Category.objects.create(organization=club, name="Material", kind="expense")
    b = buchung(c, fin, account, cats["Getränke"])
    resp = teilen(
        c,
        fin,
        b["id"],
        [
            {"category": cats["Getränke"].pk, "amount": "500.00"},
            {"category": only_expense.pk, "amount": "500.00"},
        ],
    )
    assert resp.status_code == 400
    assert "Material" in str(resp.json())


def test_teile_haengen_zusammen(c, fin, kasse):
    account, cats = kasse
    b = buchung(c, fin, account, cats["Getränke"])
    rows = teilen(
        c,
        fin,
        b["id"],
        [
            {"category": cats["Getränke"].pk, "amount": "700.00"},
            {"category": cats["Eintritt"].pk, "amount": "300.00"},
        ],
    ).json()
    part = rows[1]["id"]
    # Datum und Konto gelten für alle Teile
    resp = c.patch(f"{fin}/bookings/{part}/", {"date": "2020-06-01"}, content_type=JSON)
    assert resp.status_code == 400
    assert "Splitbuchung" in str(resp.json())
    # Kategorie eines Teils bleibt änderbar
    resp = c.patch(
        f"{fin}/bookings/{part}/", {"category": cats["Bandenwerbung"].pk}, content_type=JSON
    )
    assert resp.status_code == 200, resp.json()
    # Kopf erst löschen, wenn die Teile weg sind
    resp = c.delete(f"{fin}/bookings/{b['id']}/")
    assert resp.status_code == 400 and "übrigen Teile" in str(resp.json())
    assert c.delete(f"{fin}/bookings/{part}/").status_code == 204
    assert c.delete(f"{fin}/bookings/{b['id']}/").status_code == 204


def test_kontoumsatz_passt_zur_summe(c, fin, kasse, club, board_a):
    account, cats = kasse
    b = buchung(c, fin, account, cats["Getränke"])
    rows = teilen(
        c,
        fin,
        b["id"],
        [
            {"category": cats["Getränke"].pk, "amount": "800.00"},
            {"category": cats["Eintritt"].pk, "amount": "200.00"},
        ],
    ).json()
    with tenant_context(club.pk):
        statement = BankStatement.objects.create(
            organization=club, account=account, file_name="auszug.xml"
        )
        line = BankLine.objects.create(
            organization=club,
            statement=statement,
            account=account,
            date=timezone.localdate(),
            amount=Decimal("1000.00"),
            credit=True,
            fingerprint="test-split-1",
        )
        lead = Booking.objects.get(pk=b["id"])
        part = Booking.objects.get(pk=rows[1]["id"])
        with pytest.raises(ValidationError):
            bank_import.link_booking(line, part, board_a)
        bank_import.link_booking(line, lead, board_a)
        line.refresh_from_db()
        assert line.booking_id == lead.pk


def test_ohne_beleg_zaehlt_teile_mit_beleg_am_kopf_nicht(c, fin, kasse, club):
    account, cats = kasse
    b = buchung(c, fin, account, cats["Getränke"])
    teilen(
        c,
        fin,
        b["id"],
        [
            {"category": cats["Getränke"].pk, "amount": "800.00"},
            {"category": cats["Eintritt"].pk, "amount": "200.00"},
        ],
    )
    with tenant_context(club.pk):
        Receipt.objects.create(
            organization=club,
            booking_id=b["id"],
            name="abrechnung.pdf",
            file="x.pdf",
            content_type="application/pdf",
        )
    data = c.get(f"{fin}/bookings/?ohne_beleg=1").json()
    rows = data["results"] if isinstance(data, dict) else data
    assert rows == []
