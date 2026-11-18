"""Gesamtaudit 15.11., AZ-04: Vorstandsrollen in Untereinheiten mit eigener Kasse unter der
Rolle der Anwendung (Zeilenschutz wie im Betrieb, erfundene Daten).

Die Pauschalen zählen die Kassen der Untereinheiten mit, die steuerlich zum Verein gehören,
und markieren dabei Vorstandsmitglieder aller dieser Einheiten. Die Rollenzuordnungen einer
Untereinheit sieht der Verein unter dem Zeilenschutz nicht; sie werden in deren Bereich
gelesen. Rollen eines fremden Vereins und Rollen ohne Vorstand markieren niemanden."""
# ruff: noqa: F811

import datetime

import pytest

from access.models import Role, RoleAssignment
from core.tenancy import rls_bypass

from .factories import make_member
from .test_az04_pauschalen_untereinheiten import _untereinheit
from .test_m9_billing import c, club  # noqa: F401
from .test_pauschalen_reste import _tax, _zahlung, report

pytestmark = pytest.mark.django_db


def _amt(org, person, name="Zugführerin", is_board=True):
    """Rolle ohne Konto, nur mit Akte: Der Vorstand, der die Auswertung abruft, hält sie
    nicht selbst und sieht sie daher nicht über seine eigenen Zuordnungen."""
    with rls_bypass():
        role = Role.objects.create(organization=org, name=name, is_board=is_board)
        return RoleAssignment.objects.create(
            organization=org, role=role, person=person, valid_from=datetime.date(2020, 1, 1)
        )


def _person(data, membership):
    return next(p for p in data["people"] if p["membership"] == membership.pk)


def test_vorstand_in_der_untereinheit_wird_markiert(c, club):
    _tax(club)
    unit = _untereinheit(club)
    erika = make_member(club, "Erika", "Musterfrau")
    _zahlung(unit, erika, "200", "volunteer")
    _amt(unit, erika.person)

    data = report(c, club)
    person = _person(data, erika)
    assert person["board"] is True
    assert person["board_warning"] is True
    assert [w["kind"] for w in data["warnings"]] == ["board"]

    # Die Untereinheit selbst markiert sie ebenso
    assert _person(report(c, unit), erika)["board"] is True


def test_rolle_ohne_vorstand_markiert_nicht(c, club):
    _tax(club)
    unit = _untereinheit(club)
    max_ = make_member(club, "Max", "Mustermann")
    _zahlung(unit, max_, "200", "volunteer")
    _amt(unit, max_.person, name="Notenwart", is_board=False)

    data = report(c, club)
    assert _person(data, max_)["board"] is False
    assert data["warnings"] == []


def test_vorstand_im_fremden_verein_markiert_nicht(c, club, orgs):
    _tax(club)
    unit = _untereinheit(club)
    erika = make_member(club, "Erika", "Musterfrau")
    _zahlung(club, erika, "100", "volunteer")
    _zahlung(unit, erika, "100", "volunteer")
    # Vorstandsrolle derselben Akte in einem fremden Verein (nur zur Probe des Filters)
    _amt(orgs["b"], erika.person, name="Vorsitzende")

    data = report(c, club)
    assert _person(data, erika)["board"] is False
    assert data["warnings"] == []
