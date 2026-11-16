"""Namenswiderspruch in allen öffentlichen Ausgaben; unbekanntes Geburtsdatum wie minderjährig.

Gesamtaudit 15.11., PF-05 (Fachfrage FF-25): „Namen aus Chronik und Ehrungen entfernen“
ließ den Namen in Ranglisten, Startlisten und Preisen stehen, solange die Person noch in einem
anderen Verein Mitglied war. PF-21 (FF-24): Ohne Geburtsdatum galt ein Mitglied als
volljährig, seine Ergebnisse erschienen ohne Einwilligung mit Namen. Erfundene Daten.
"""

import datetime
from types import SimpleNamespace

import pytest

from competitions.models import Competition, Prize, Starter
from core.tenancy import rls_bypass, tenant_context
from members.models import Membership, Person
from members.workflows import NAME_REMOVED, erase_history, purge_membership
from website import services
from website.models import PublicationConsent, Website
from website.results import WITHOUT_NAME, Names

from .factories import make_member, make_org

pytestmark = pytest.mark.django_db
Category = PublicationConsent.Category


def _names(comp, memberships) -> Names:
    site = SimpleNamespace(
        people=SimpleNamespace(load=lambda ids: None),
        consents=services.active_entries([m.pk for m in memberships]),
        site=SimpleNamespace(name_format=Website.NameFormat.FULL, show_titles=False),
    )
    return Names(site, comp)


def _comp(club, date=datetime.date(2026, 6, 1)):
    return Competition.objects.create(
        organization=club, title="Königsschießen", date=date, form=Competition.Form.BIRD
    )


def test_widerspruch_gilt_ueberall_auch_mit_zweitem_verein():
    club = make_org("Verein Widerspruch")
    other = make_org("Anderer Verein")
    member = make_member(club, "Erika", "Muster", birth_date=datetime.date(1970, 3, 4))
    with rls_bypass():
        # Dieselbe Person ist noch im anderen Verein Mitglied: ihr Name bleibt an der Person
        Membership.objects.create(organization=other, scope=other, person=member.person)
    with tenant_context(club.pk):
        comp = _comp(club)
        starter = Starter.objects.create(
            organization=club, competition=comp, membership=member, name="Erika Muster"
        )
        prize = Prize.objects.create(
            organization=club,
            competition=comp,
            name="Krone",
            winner=starter,
            winner_name="Erika Muster",
        )
        services.set_entry(member, Category.RESULTS_MINOR, True, "board", None)
        purge_membership(Membership.objects.get(pk=member.pk), after_deadline=True)
        counts = erase_history(Membership.objects.get(pk=member.pk))
    assert counts["Widersprüche"] == len(PublicationConsent.OBJECTION_CATEGORIES)
    with rls_bypass():
        starter.refresh_from_db()
        prize.refresh_from_db()
        person = Person.objects.get(pk=member.person_id)
        active = services.active_entries([member.pk])[member.pk]
    assert person.last_name == "Muster"  # noch im anderen Verein
    assert starter.name == NAME_REMOVED and prize.winner_name == NAME_REMOVED
    assert active == set(PublicationConsent.OBJECTION_CATEGORIES)  # Einwilligungen beendet
    with tenant_context(club.pk):
        names = _names(comp, [member])
        assert names.of(Membership.objects.get(pk=member.pk), "Erika Muster") == WITHOUT_NAME
        assert names.of_starter(starter.pk) == WITHOUT_NAME
        # Nochmals (Löschliste): nichts Neues
        assert erase_history(Membership.objects.get(pk=member.pk))["Widersprüche"] == 0


def test_ohne_geburtsdatum_wie_minderjaehrig():
    club = make_org("Verein Alter")
    unknown = make_member(club, "Max", "Ohnedatum")
    adult = make_member(club, "Anna", "Erwachsen", birth_date=datetime.date(1980, 1, 1))
    year_only = make_member(club, "Paul", "Jahrgang", birth_date=datetime.date(2008, 1, 1))
    with rls_bypass():
        nobody = Person.objects.get(pk=unknown.person_id)
        nobody.birth_date = None
        nobody.save(update_fields=["birth_date"])
        person = Person.objects.get(pk=year_only.person_id)
        person.birth_year_only = True
        person.save(update_fields=["birth_year_only"])
    with tenant_context(club.pk):
        comp = _comp(club, datetime.date(2026, 6, 1))
        members = [Membership.objects.get(pk=m.pk) for m in (unknown, adult, year_only)]
        names = _names(comp, members)
        # Ohne Geburtsdatum und nur mit Jahrgang 2008 (am 1.6.2026 so jung wie möglich: 17)
        assert names.of(members[0], "") == WITHOUT_NAME
        assert names.of(members[1], "") == "Anna Erwachsen"
        assert names.of(members[2], "") == WITHOUT_NAME
        # Mit Einwilligung „Wettbewerbsergebnisse unter 18“ erscheint der Name
        services.set_entry(members[0], Category.RESULTS_MINOR, True, "board", None)
        assert _names(comp, members).of(members[0], "") == "Max Ohnedatum"
