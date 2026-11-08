"""Aufwandsvergütungen, Reste aus S3 (Konzept vereinskasse-steuern): Verzicht als
Aufwandsspende, Musikerabrechnung und Untereinheiten (erfundene Daten)."""
# ruff: noqa: F811

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from core.tenancy import tenant_context
from finance.models import Account, Booking, Category
from organizations.models import Department

from .factories import make_member
from .test_music import JSON, c, club, music  # noqa: F401
from .test_music_settlement import expense, post, settlement  # noqa: F401

pytestmark = pytest.mark.django_db


def _tax(org):
    org.enabled_modules = sorted({*(org.enabled_modules or []), "finance", "members", "tax"})
    org.save()


def report(c, org):
    resp = c.get(f"/api/orgs/{org.pk}/finance/allowances/", {"jahr": timezone.localdate().year})
    assert resp.status_code == 200, resp.content
    return resp.json()


def spende(c, org, **data):
    body = {
        "date": timezone.localdate().isoformat(),
        "kind": "money",
        "amount": "300.00",
        "donor_name": "Erika Musterfrau",
        "donor_address": "Musterweg 1, 12345 Musterstadt",
        **data,
    }
    return c.post(f"/api/orgs/{org.pk}/finance/donations/", body, content_type=JSON)


def test_verzicht_auf_pauschale_zaehlt_gegen_freibetrag(c, club):
    _tax(club)
    erika = make_member(club, "Erika", "Musterfrau")
    # Ohne Verzicht keine Pauschale
    bad = spende(c, club, allowance="volunteer", membership=erika.pk)
    assert bad.status_code == 400 and "allowance" in bad.json()
    ok = spende(c, club, allowance="volunteer", waiver=True, membership=erika.pk)
    assert ok.status_code == 201, ok.content
    # Ein Verzicht auf Fahrtkosten zählt nicht
    assert spende(c, club, waiver=True, amount="40.00").status_code == 201
    data = report(c, club)
    assert len(data["people"]) == 1
    person = data["people"][0]
    assert person["membership"] == erika.pk
    assert person["kinds"][0]["kind"] == "volunteer"
    assert Decimal(person["kinds"][0]["total"]) == Decimal("300.00")
    assert person["bookings"][0]["source"] == "waiver"


def test_musikerauszahlung_zaehlt_beim_musiker(c, club, settlement):
    _tax(club)
    url, assignment = settlement
    assert post(c, url, action="agreement", fee="100", travel="0", extras="0").status_code == 200
    r = post(
        c,
        url,
        action="claim",
        assignment=assignment.pk,
        fee="40",
        allowance="10",
        expenses="0",
        attended=True,
    )
    claim = r.json()["claims"][0]["id"]
    assert post(c, url, action="approve", claim=claim).status_code == 200
    booking = expense(c, club, "50")
    assert post(c, url, action="payment", claim=claim, booking=booking).status_code == 200
    with tenant_context(club.pk):
        assert Booking.objects.get(pk=booking).allowance == "trainer"
    data = report(c, club)
    assert [p["name"] for p in data["people"]] == ["Alex Beispiel"]
    assert data["people"][0]["kinds"][0]["total"] == "50.00"
    assert data["warnings"] == []
    # Vergütungsart im Kassenbuch entfernt: Hinweis auf die Musikerabrechnung
    bookings = f"/api/orgs/{club.pk}/finance/bookings/{booking}/"
    resp = c.patch(bookings, {"allowance": ""}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    data = report(c, club)
    assert data["people"] == []
    assert [w["kind"] for w in data["warnings"]] == ["music"]
    # … und wieder gesetzt, auch ohne Empfänger: die Person steht in der Musikerakte
    resp = c.patch(bookings, {"allowance": "trainer"}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    assert report(c, club)["warnings"] == []


def test_ohne_steuermodul_bleibt_die_buchung_unveraendert(c, club, settlement):
    club.enabled_modules = [m for m in club.enabled_modules if m != "tax"]
    club.save()
    url, assignment = settlement
    post(c, url, action="agreement", fee="100", travel="0", extras="0")
    r = post(
        c,
        url,
        action="claim",
        assignment=assignment.pk,
        fee="50",
        allowance="0",
        expenses="0",
        attended=True,
    )
    claim = r.json()["claims"][0]["id"]
    post(c, url, action="approve", claim=claim)
    booking = expense(c, club, "50")
    assert post(c, url, action="payment", claim=claim, booking=booking).status_code == 200
    with tenant_context(club.pk):
        assert Booking.objects.get(pk=booking).allowance == ""


def _zahlung(org, membership, amount, allowance="trainer"):
    with tenant_context(org.pk):
        account = Account.objects.create(
            organization=org, name="Kasse", kind="cash", opening_date=datetime.date(2020, 1, 1)
        )
        cat = Category.objects.create(organization=org, name="Übungsleiter")
        day = timezone.localdate()
        return Booking.objects.create(
            organization=org,
            year=org.fiscal_year_of(day),
            number=Booking.objects.filter(organization=org).count() + 1,
            date=day,
            kind="expense",
            amount=Decimal(amount),
            account=account,
            category=cat,
            text="Übungsleitervergütung",
            membership=membership,
            allowance=allowance,
        )


def test_untereinheiten_werden_je_person_zusammengezaehlt(c, club):
    _tax(club)
    unit = Department.objects.create(organization=club, name="Spielmannszug", founding_year=1980)
    resp = c.patch(
        f"/api/orgs/{club.pk}/departments/{unit.pk}/", {"own_workspace": True}, content_type=JSON
    )
    assert resp.status_code == 200, resp.json()
    unit.refresh_from_db()
    unit.enabled_modules = sorted({*(unit.enabled_modules or []), "finance", "tax"})
    unit.save()
    erika = make_member(club, "Erika", "Musterfrau")
    limit = Decimal("2000")
    _zahlung(club, erika, limit)
    _zahlung(unit, erika, limit)
    data = report(c, club)
    assert data["units"] == ["Spielmannszug"]
    person = next(p for p in data["people"] if p["membership"] == erika.pk)
    assert Decimal(person["kinds"][0]["total"]) == 2 * limit
    assert person["kinds"][0]["status"] == "over"
    assert {b["unit"] for b in person["bookings"]} == {"", "Spielmannszug"}
    # Die Untereinheit sieht nur ihre eigene Kasse und den Hinweis, wo sie mitzählt
    own = report(c, unit)
    assert own["counted_at"] == club.name
    assert Decimal(own["people"][0]["kinds"][0]["total"]) == limit
