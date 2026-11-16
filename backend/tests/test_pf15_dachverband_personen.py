"""Vereinslöschung im Dachverband lässt keine Personen zurück (Gesamtaudit 15.11., PF-15).

Bestätigt: Personen eines Vereins im Dachverband liegen im Bereich des Dachverbands
(``Person.scope``). Wurde der Verein gelöscht, blieben Person, gemeinsame Kontaktdaten und
Verbandsmeldung ohne Mitgliedschaft stehen, und kein Löschlauf fand sie mehr. Erfundene Daten.
"""

# ruff: noqa: F811  (Fixtures als Parameter)

import pytest

from core.tenancy import rls_bypass
from members.models import ContactDetails, Membership, Person

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
