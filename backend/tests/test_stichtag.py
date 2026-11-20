"""Stichtagsstatistik: Mitglieder an einem Tag nach Alter, Geschlecht, Wohnort und Abteilung."""

import datetime

import pytest

from core.tenancy import rls_bypass, tenant_context
from members import workflows
from members.models import ContactDetails, MemberType, Person
from organizations.models import Department

from .factories import give_role, make_member, make_user

pytestmark = pytest.mark.django_db
D = datetime.date


def _set(member, gender: str, city: str, plz: str):
    with rls_bypass():
        Person.objects.filter(pk=member.person_id).update(gender=gender)
        ContactDetails.objects.filter(person_id=member.person_id).update(city=city, postal_code=plz)


@pytest.fixture
def verein(orgs):
    club = orgs["a"]
    club.enabled_modules = ["members"]
    club.save()
    with tenant_context(club.pk):
        aktiv = MemberType.objects.create(organization=club, name="aktiv", active=True)
        passiv = MemberType.objects.create(organization=club, name="passiv", reported=False)
        fussball = Department.objects.create(organization=club, name="Fußball")
        tennis = Department.objects.create(organization=club, name="Tennis")
    # Erfundene Mitglieder; Stichtag in den Tests: 1. Januar 2026
    kind = make_member(
        club, "Kai", "Klein", member_type=aktiv, birth_date=D(2019, 6, 1), departments=[fussball]
    )
    jugend = make_member(
        club,
        "Jana",
        "Jung",
        member_type=aktiv,
        birth_date=D(2011, 1, 1),
        departments=[fussball, tennis],
    )
    # Wird im Laufe von 2026 erst 27: nach Jahrgang 27, am Stichtag 26
    mitte = make_member(club, "Mia", "Mitte", member_type=passiv, birth_date=D(1999, 12, 31))
    alt = make_member(club, "Otto", "Alt", member_type=aktiv, birth_date=D(1950, 3, 3))
    weg = make_member(club, "Wim", "Weg", member_type=aktiv, birth_date=D(1980, 1, 1))
    spaet = make_member(club, "Sina", "Spät", member_type=aktiv, entry_date=D(2026, 2, 1))
    _set(kind, "männlich", "Musterstadt", "12345")
    _set(jugend, "weiblich", "musterstadt", "12346")
    _set(mitte, "divers", "Beispielheim", "54321")
    _set(alt, "", "", "")
    _set(weg, "männlich", "Musterstadt", "12345")
    _set(spaet, "weiblich", "Musterstadt", "12345")
    with tenant_context(club.pk):
        # Austritt am Stichtag: zählt nicht mehr mit
        workflows.exit_membership(weg, D(2026, 1, 1), "exit")
    return {"club": club, "aktiv": aktiv, "passiv": passiv}


def get(c, url, **params):
    resp = c.get(url, params)
    assert resp.status_code == 200, resp.content
    return resp.json()


def url(verein):
    return f"/api/orgs/{verein['club'].pk}/members/statistics/stichtag/"


class TestStichtag:
    def test_alter_geschlecht_wohnort(self, api, board_a, verein):
        data = get(api(board_a), url(verein), stichtag="2026-01-01")
        assert data["stichtag"] == "2026-01-01"
        assert data["total"] == 4
        assert data["persons"] == 4
        assert data["organizations"] == 0
        assert data["age_groups"] == [
            "bis 6",
            "7 bis 14",
            "15 bis 18",
            "19 bis 26",
            "27 bis 40",
            "41 bis 60",
            "über 60",
        ]
        rows = {r["label"]: r["counts"] for r in data["rows"]}
        # männlich, weiblich, divers, ohne Angabe
        assert rows["bis 6"] == [1, 0, 0, 0]
        assert rows["15 bis 18"] == [0, 1, 0, 0]
        assert rows["19 bis 26"] == [0, 0, 1, 0]
        assert rows["über 60"] == [0, 0, 0, 1]
        assert data["genders"] == [1, 1, 1, 1]
        places = {p["city"]: p for p in data["places"]}
        # Groß- und Kleinschreibung zählen als ein Ort, PLZ werden gesammelt
        assert places["Musterstadt"]["total"] == 2
        assert places["Musterstadt"]["postal_codes"] == ["12345", "12346"]
        assert places["Beispielheim"]["total"] == 1
        assert places["ohne Anschrift"]["missing"] is True
        assert data["places"][-1]["city"] == "ohne Anschrift"
        groups = {g["name"]: g["total"] for g in data["groups"]}
        # Jana ist in beiden Abteilungen und zählt in jeder
        assert groups == {"Fußball": 2, "Tennis": 1}

    def test_jahrgang_und_altersgruppen(self, api, board_a, verein):
        data = get(
            api(board_a), url(verein), stichtag="2026-01-01", zaehlung="jahrgang", alter="jugend"
        )
        rows = {r["label"]: r["total"] for r in data["rows"]}
        # Jana (Jahrgang 2011) zählt 15, Mia (1999) zählt 27
        assert rows["14 bis 17"] == 1
        assert rows["27 und älter"] == 2
        assert rows["18 bis 26"] == 0

    def test_mitgliedsarten_auswaehlen(self, api, board_a, verein):
        data = get(api(board_a), url(verein), stichtag="2026-01-01", arten=str(verein["aktiv"].pk))
        assert data["total"] == 3
        types = {t["name"]: t["count"] for t in data["types"]}
        assert types == {"aktiv": 3, "passiv": 1}

    def test_dateien(self, api, board_a, verein):
        c = api(board_a)
        for fmt, start in (("pdf", b"%PDF"), ("xlsx", b"PK"), ("csv", "﻿".encode())):
            resp = c.get(url(verein), {"stichtag": "2026-01-01", "als": fmt})
            assert resp.status_code == 200
            assert resp.content.startswith(start)
            assert "Mitglieder-Stichtag-2026-01-01" in resp["Content-Disposition"]
        text = c.get(url(verein), {"stichtag": "2026-01-01", "als": "csv"}).content.decode()
        assert "Musterstadt (12345, 12346)" in text

    def test_ungueltige_angaben(self, api, board_a, verein):
        c = api(board_a)
        assert c.get(url(verein), {"stichtag": "1.1.2026"}).status_code == 400
        assert c.get(url(verein), {"alter": "x"}).status_code == 400

    def test_ohne_mitgliederrecht(self, api, verein):
        user = make_user("kasse@example.org")
        give_role(user, verein["club"], ["finance.view"], name="Kasse")
        assert api(user).get(url(verein)).status_code == 403

    def test_dachverband(self, api, orgs, verein):
        fed = orgs["federation"]
        fed.federation_member_access = "read"
        fed.save()
        user = make_user("verband@example.org")
        give_role(user, fed)
        data = get(
            api(user), f"/api/orgs/{fed.pk}/federation/statistics/stichtag/", stichtag="2026-01-01"
        )
        # Nur gemeldete Mitgliedsarten: Mia (passiv) fehlt
        assert data["total"] == 3
        assert data["groups_title"] == "Verein"
        assert [g["name"] for g in data["groups"]] == ["Verein A"]
