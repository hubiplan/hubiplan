"""Vereinslöschung im Dachverband lässt keine Personen zurück (Gesamtaudit 15.11., PF-15).

Bestätigt: Personen eines Vereins im Dachverband liegen im Bereich des Dachverbands
(``Person.scope``). Wurde der Verein gelöscht, blieben Person, gemeinsame Kontaktdaten und
Verbandsmeldung ohne Mitgliedschaft stehen, und kein Löschlauf fand sie mehr. Erfundene Daten.
"""

# ruff: noqa: F811  (Fixtures als Parameter)

import datetime

import pytest

from core.tenancy import rls_bypass
from honors.models import Dignity, Reign
from members.models import ContactDetails, HonoraryTitle, HonoraryTitleAward, Membership, Person

from .factories import make_member
from .test_platform_erasure import admin, erase, later  # noqa: F401  (Fixtures, Hilfe)

pytestmark = pytest.mark.django_db


def test_personen_nur_dieses_vereins_gehen_mit(api, admin, orgs):
    club, other, federation = orgs["a"], orgs["b"], orgs["federation"]
    only_here = make_member(club, "Erika", "Nurhier")
    both = make_member(club, "Max", "Beides")
    with rls_bypass():
        person = Person.objects.get(memberships__pk=only_here.pk)
        assert person.scope_id == federation.pk  # Personen liegen beim Dachverband
        twice = Person.objects.get(memberships__pk=both.pk)
        Membership.objects.create(organization=other, scope=federation, person=twice)
    resp = erase(api, admin, club)
    assert resp.status_code in (200, 204), resp.content
    with rls_bypass():
        # Vorher blieb sie ohne Mitgliedschaft stehen
        assert not Person.objects.filter(pk=person.pk).exists()
        assert not ContactDetails.objects.filter(person_id=person.pk).exists()
        # Wer noch in Verein B ist, bleibt
        assert Person.objects.filter(pk=twice.pk).exists()
        assert Membership.objects.filter(person=twice, organization=other).exists()


def test_person_mit_verbandsehrung_oder_wuerde_bleibt(api, admin, orgs):
    """Nur im gelöschten Verein Mitglied, aber im Dachverband geehrt bzw. mit Würde: Die Person
    bleibt, Ehrung und Würde bleiben unverändert (vorher hätte CASCADE die Ehrung still gelöscht
    und SET_NULL die Würde von der Person getrennt)."""
    club, federation = orgs["a"], orgs["federation"]
    honored = make_member(club, "Erika", "Geehrt")
    crowned = make_member(club, "Max", "Gekroent")
    with rls_bypass():
        person = Person.objects.get(memberships__pk=honored.pk)
        king = Person.objects.get(memberships__pk=crowned.pk)
        title = HonoraryTitle.objects.create(organization=federation, name="Verbandsehrennadel")
        award = HonoraryTitleAward.objects.create(
            organization=federation,
            person=person,
            title=title,
            valid_from=datetime.date(2020, 5, 1),
        )
        dignity = Dignity.objects.create(organization=federation, name="Verbandskönig")
        reign = Reign.objects.create(
            organization=federation, dignity=dignity, year=2021, person=king
        )
    resp = erase(api, admin, club)
    assert resp.status_code in (200, 204), resp.content
    with rls_bypass():
        assert Person.objects.filter(pk=person.pk).exists()
        assert HonoraryTitleAward.objects.filter(pk=award.pk, person=person).exists()
        assert Person.objects.filter(pk=king.pk).exists()
        reign.refresh_from_db()
        assert reign.person_id == king.pk
