"""Gesamtaudit 15.11., AZ-04: Aufwandsvergütungen der Untereinheiten mit eigener Kasse unter
der Rolle der Anwendung (Zeilenschutz wie im Betrieb, erfundene Daten).

Der Verein sieht die Kasse einer Untereinheit nur in deren Bereich, die Untereinheit die
Mitgliedschaften nur im Bereich des Vereins. Zahlungen an dieselbe Person zählen trotzdem
zusammen, und nichts aus einem fremden Verein fließt ein."""
# ruff: noqa: F811

from decimal import Decimal

import pytest
from django.utils import timezone

from core.tenancy import tenant_context
from finance.models import Donation
from organizations.models import Department

from . import test_pauschalen_reste as reste
from .factories import make_member
from .test_m9_billing import c, club  # noqa: F401
from .test_pauschalen_reste import _tax, _zahlung, report

pytestmark = pytest.mark.django_db


def _untereinheit(club):
    unit = Department.objects.create(
        organization=club, name="Spielmannszug", founding_year=1980, own_workspace=True
    )
    unit.enabled_modules = sorted({*(unit.enabled_modules or []), "finance", "tax"})
    unit.save()
    return unit


def test_bisheriger_ablauf_unter_app_rolle(c, club):
    """Der Ablauf aus ``test_pauschalen_reste`` läuft unverändert, nur unter der Rolle der
    Anwendung: Verein zählt Verein und Untereinheit zusammen, die Untereinheit sieht ihre
    eigene Kasse."""
    reste.test_untereinheiten_werden_je_person_zusammengezaehlt(c, club)


def test_untereinheit_zaehlt_mit_und_fremder_verein_nicht(c, club, orgs, api, board_b):
    _tax(club)
    unit = _untereinheit(club)
    erika = make_member(club, "Erika", "Musterfrau")
    own = _zahlung(club, erika, "100")
    in_unit = _zahlung(unit, erika, "200")
    with tenant_context(unit.pk):
        waiver = Donation.objects.create(
            organization=unit,
            date=timezone.localdate(),
            amount=Decimal("50.00"),
            waiver=True,
            allowance="volunteer",
            membership=erika,
            donor_name="Erika Musterfrau",
        )
    # Fremder Verein mit einer Person gleichen Namens und eigener Pauschale
    other = orgs["b"]
    _tax(other)
    erika_b = make_member(other, "Erika", "Musterfrau")
    foreign = _zahlung(other, erika_b, "500")

    data = report(c, club)
    assert data["units"] == ["Spielmannszug"]
    assert len(data["people"]) == 1
    person = data["people"][0]
    assert person["membership"] == erika.pk
    assert person["name"] == "Erika Musterfrau"
    totals = {k["kind"]: Decimal(k["total"]) for k in person["kinds"]}
    assert totals == {"trainer": Decimal("300.00"), "volunteer": Decimal("50.00")}
    ids = {(b["source"], b["id"]) for b in person["bookings"]}
    assert ids == {("booking", own.pk), ("booking", in_unit.pk), ("waiver", waiver.pk)}
    assert ("booking", foreign.pk) not in ids
    assert {b["unit"] for b in person["bookings"]} == {"", "Spielmannszug"}

    # Die Untereinheit sieht ihre eigenen Zahlungen, der Person zugeordnet
    mine = report(c, unit)
    assert mine["counted_at"] == club.name
    assert [p["membership"] for p in mine["people"]] == [erika.pk]
    assert mine["people"][0]["name"] == "Erika Musterfrau"
    assert {b["id"] for b in mine["people"][0]["bookings"]} == {in_unit.pk, waiver.pk}

    # Der fremde Verein sieht nur seine eigene Zahlung
    theirs = report(api(board_b), other)
    assert [p["membership"] for p in theirs["people"]] == [erika_b.pk]
    assert Decimal(theirs["people"][0]["kinds"][0]["total"]) == Decimal("500.00")
