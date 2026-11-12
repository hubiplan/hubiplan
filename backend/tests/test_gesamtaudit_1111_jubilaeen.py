"""Gesamtaudit 11.11.2026, P-03: Jubiläen und Geburtstage ohne Abfragen je Mitglied."""

import datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.tenancy import tenant_context
from members import services
from members.birthdays import birthdays_between
from members.duration import jubilees_between
from members.models import MemberType

from .factories import make_member

pytestmark = pytest.mark.django_db

VON, BIS = datetime.date(2025, 1, 1), datetime.date(2025, 12, 31)


def admit(club, count, start=0):
    return [
        make_member(
            club,
            f"Vorname{i}",
            f"Nachname{i:02d}",
            entry_date=datetime.date(2000, 3, 1 + i),
            birth_date=datetime.date(1970, 6, 1 + i),
        )
        for i in range(start, start + count)
    ]


def measured(club, call):
    with tenant_context(club.pk), CaptureQueriesContext(connection) as queries:
        rows = call(club, VON, BIS)
    return rows, len(queries)


def test_jubilaeen_abfragen_wachsen_nicht_mit_der_mitgliederzahl(orgs):
    club, federation = orgs["a"], orgs["federation"]
    club.jubilee_years = [25]
    club.save()
    federation.jubilee_years = [25]
    federation.save()
    admit(club, 2)
    few_rows, few = measured(club, jubilees_between)
    admit(club, 6, start=2)
    rows, many = measured(club, jubilees_between)
    assert many == few
    assert len(few_rows) == 4 and len(rows) == 16
    assert {r["kind"] for r in rows} == {"club", "federation"}
    first = rows[0]
    assert (first["last_name"], first["first_name"]) == ("Nachname00", "Vorname0")
    assert first["date"] == datetime.date(2025, 3, 1) and first["years"] == 25
    assert first["birth_date"] == datetime.date(1970, 6, 1)


def test_verbandszeit_zaehlt_ueber_vereine_hinweg(orgs):
    """Zeiten im anderen Verein des Dachverbands zählen für das Verbandsjubiläum mit."""
    club, other, federation = orgs["a"], orgs["b"], orgs["federation"]
    federation.jubilee_years = [25]
    federation.save()
    club.jubilee_years = []
    club.save()
    first = make_member(other, "Anna", "Muster", entry_date=datetime.date(2000, 5, 1))
    with tenant_context(club.pk):
        passive = MemberType.objects.create(organization=club, name="passiv", active=False)
        services.admit(
            club,
            {
                "person": first.person,
                "member_type": passive,
                "entry_date": datetime.date(2010, 1, 1),
                "departments": [],
            },
        )
    rows, _ = measured(club, jubilees_between)
    assert [(r["kind"], r["years"], r["date"]) for r in rows] == [
        ("federation", 25, datetime.date(2025, 5, 1))
    ]


def test_geburtstage_abfragen_wachsen_nicht_mit_der_mitgliederzahl(orgs):
    club = orgs["a"]
    admit(club, 2)
    _, few = measured(club, birthdays_between)
    admit(club, 6, start=2)
    rows, many = measured(club, birthdays_between)
    assert many == few
    assert [(r["last_name"], r["first_name"], r["age"]) for r in rows[:2]] == [
        ("Nachname00", "Vorname0", 55),
        ("Nachname01", "Vorname1", 55),
    ]
    assert len(rows) == 8 and rows[0]["date"] == datetime.date(2025, 6, 1)
