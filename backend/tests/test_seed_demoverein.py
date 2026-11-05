"""Zusätzlicher Demoverein mit Korps (Testserver, alles erfunden)."""

import io

import pytest
from django.core.management import call_command

from access.catalog import SWITCHABLE_MODULES
from accounts.models import User
from competitions.models import Competition
from entries.models import Entry
from finance.models import Booking
from honors.models import Dignity
from materials.models import MaterialItem
from members.models import ContactDetails, Membership
from music.models import Assignment, Musician, Performance, Piece
from organizations import demo_korps
from organizations.models import Department, Organization
from todos.models import Todo, TodoShare
from website.models import Website

pytestmark = [pytest.mark.django_db, pytest.mark.langsam]


def seed():
    out = io.StringIO()
    call_command("seed_demoverein", password="Test-Passwort-123", stdout=out)
    return out.getvalue()


def test_verein_mit_korps_und_zuegen():
    out = seed()
    club = Organization.objects.get(name=demo_korps.CLUB_NAME)
    assert club.type == "club" and club.parent.type == "platform"
    assert set(SWITCHABLE_MODULES) <= set(club.enabled_modules)
    assert club.member_portal_enabled and club.department_access_enabled
    korps = Department.objects.filter(organization=club, parent=club).order_by("sort_order")
    assert [k.name for k in korps] == [k[0] for k in demo_korps.KORPS]
    assert all(k.label == "Korps" for k in korps)
    jaeger = korps.get(name="Jägerkorps")
    zuege = Department.objects.filter(parent=jaeger)
    assert zuege.count() == 4 and all(z.label == "Zug" for z in zuege)
    # Tambourkorps ohne Züge, Mitglieder direkt im Korps
    tambour = korps.get(name="Tambourkorps Musterstadt")
    assert not Department.objects.filter(parent=tambour).exists()
    assert tambour.unit_memberships.count() >= 18
    assert Membership.objects.filter(organization=club).count() > 200
    assert all(c.email.endswith(".test") for c in ContactDetails.objects.all())
    # Daten in den Modulen
    assert Booking.objects.filter(organization=club).exists()
    assert Competition.objects.filter(organization=club, status="endgueltig").count() == 2
    assert Entry.objects.filter(organization=club).count() == 4
    assert Dignity.objects.filter(organization=club, unit__isnull=False).count() == 7
    assert Website.objects.filter(organization=club).exists()
    # Musik, Aufgaben, Material (Bildschirmfotos der Produktwebseite)
    assert Musician.objects.filter(organization=club, membership__isnull=False).count() >= 14
    performance = Performance.objects.get(organization=club)
    assert Assignment.objects.filter(performance=performance).count() >= 15
    assert performance.program_entries.count() == 4
    assert Piece.objects.filter(organization=club).count() == len(demo_korps.STUECKE)
    assert Todo.objects.filter(organization=club).count() == 5
    assert TodoShare.objects.filter(organization=club).count() == 3
    assert MaterialItem.objects.filter(organization=club, kind="material").count() == 6
    # Schützenhaus mit Saal und Luftgewehrstand; der Schlüssel gehört zum Haus
    facilities = {
        i.title: i for i in MaterialItem.objects.filter(organization=club, kind="facility")
    }
    assert set(facilities) == {"Schützenhaus", "Saal", "Luftgewehrstand"}
    key = MaterialItem.objects.get(organization=club, belongs_to__isnull=False)
    assert key.belongs_to == facilities["Schützenhaus"]
    assert "Passwort: Test-Passwort-123" not in out
    assert set(User.objects.values_list("email", flat=True)) == set(demo_korps.all_emails())


def test_wiederholbar_und_laesst_pilotdaten_unveraendert():
    call_command("seed_testdata", password="Test-Passwort-123", stdout=io.StringIO())
    before = {
        o.pk: Membership.objects.filter(organization=o).count()
        for o in Organization.objects.exclude(type="unit")
    }
    seed()
    club = Organization.objects.get(name=demo_korps.CLUB_NAME)
    count = Membership.objects.filter(organization=club).count()
    seed()
    assert Membership.objects.filter(organization=club).count() == count
    after = {
        o.pk: Membership.objects.filter(organization=o).count()
        for o in Organization.objects.exclude(type="unit").exclude(pk=club.pk)
    }
    assert after == before


def test_zugaenge_melden_sich_an(client):
    seed()
    for email in demo_korps.all_emails():
        user = User.objects.get(email=email)
        assert user.check_password("Test-Passwort-123"), email
