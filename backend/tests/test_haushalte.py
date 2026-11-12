"""Haushalte und Firmen (Konzept Familien, Haushalte und Firmen, H1): anlegen, Mitglieder
zuordnen mit Zeitraum, Vorschläge aus gleicher Anschrift, ein Brief je Haushalt."""
# ruff: noqa: F811  (Fixtures aus test_m12_events als Parameter)

import datetime

import pytest

from audit.models import AuditEntry
from circulars.models import CircularRecipient
from members.households import letter_name
from members.models import ContactDetails, Household, HouseholdMember, Membership, today
from members.workflows import _purge_membership, exit_membership

from .factories import make_member, make_user
from .test_m12_events import JSON, board_fed, cal, private_root  # noqa: F401  (Fixtures)
from .test_rundschreiben import base, draft, preview, send, without_email

pytestmark = pytest.mark.django_db


def hh_url(org, pk=None, suffix=""):
    root = f"/api/orgs/{org.pk}/households/"
    return f"{root}{pk}/{suffix}" if pk else f"{root}{suffix}"


@pytest.fixture
def family(cal):
    club = cal["a"]
    return {
        "erika": make_member(club, "Erika", "Muster", email="familie@example.org"),
        "max": make_member(club, "Max", "Muster", email="max@example.org"),
        "lisa": make_member(
            club,
            "Lisa",
            "Muster",
            email="familie@example.org",
            birth_date=datetime.date(2012, 1, 1),
        ),
        "otto": make_member(club, "Otto", "Other", email="otto@example.org"),
    }


def new_household(client, org, name="Familie Muster", kind="family"):
    resp = client.post(hh_url(org), {"name": name, "kind": kind}, content_type=JSON)
    assert resp.status_code == 201, resp.json()
    return resp.json()


def add(client, org, hh, membership, **extra):
    return client.post(
        hh_url(org, hh["id"], "members/"),
        {"membership": membership.pk, **extra},
        content_type=JSON,
    )


class TestHaushalt:
    def test_anlegen_zuordnen_akte_und_liste(self, api, cal, board_a, family):
        c = api(board_a)
        club = cal["a"]
        hh = new_household(c, club)
        resp = add(c, club, hh, family["erika"], role="adult")
        assert resp.status_code == 201, resp.json()
        add(c, club, hh, family["lisa"], role="child")
        data = c.get(hh_url(club, hh["id"])).json()
        assert [m["first_name"] for m in data["members"]] == ["Erika", "Lisa"]
        assert data["members"][0]["role"] == "adult"
        akte = c.get(f"/api/orgs/{club.pk}/members/{family['erika'].pk}/").json()
        assert akte["households"][0]["name"] == "Familie Muster"
        assert [o["name"] for o in akte["households"][0]["others"]] == ["Lisa Muster"]
        rows = c.get(f"/api/orgs/{club.pk}/members/?haushalt=mit").json()["results"]
        assert {r["first_name"] for r in rows} == {"Erika", "Lisa"}
        assert rows[0]["households"][0]["name"] == "Familie Muster"
        rows = c.get(f"/api/orgs/{club.pk}/members/?haushalt=ohne").json()["results"]
        assert {r["first_name"] for r in rows} == {"Max", "Otto"}
        rows = c.get(f"/api/orgs/{club.pk}/members/?haushalt={hh['id']}").json()["results"]
        assert len(rows) == 2
        assert AuditEntry.objects.filter(action="create").exists()

    def test_nur_ein_familienhaushalt_aber_zusaetzlich_firma(self, api, cal, board_a, family):
        c = api(board_a)
        club = cal["a"]
        one = new_household(c, club)
        two = new_household(c, club, "Familie Zwei")
        firm = new_household(c, club, "Musterbau GmbH", kind="company")
        start = str(today() - datetime.timedelta(days=10))
        assert add(c, club, one, family["max"], valid_from=start).status_code == 201
        resp = add(c, club, two, family["max"])
        assert resp.status_code == 400 and "Familie Muster" in str(resp.json())
        # Firma geht zusätzlich (FH-3), Rolle gibt es dort nicht
        resp = add(c, club, firm, family["max"], role="adult")
        assert resp.status_code == 201
        assert resp.json()["members"][0]["role"] == ""
        # Wechseln: bisherige Zugehörigkeit endet am Vortag
        resp = add(c, club, two, family["max"], move=True, valid_from=str(today()))
        assert resp.status_code == 201, resp.json()
        old = HouseholdMember.objects.get(household_id=one["id"])
        assert old.valid_until == today() - datetime.timedelta(days=1)

    def test_beenden_loeschen_und_rechte(self, api, cal, board_a, family):
        c = api(board_a)
        club = cal["a"]
        hh = new_household(c, club)
        start = str(today() - datetime.timedelta(days=10))
        link = add(c, club, hh, family["erika"], valid_from=start).json()["members"][0]["link"]
        assert c.delete(hh_url(club, hh["id"])).status_code == 400
        resp = c.patch(
            hh_url(club, hh["id"], f"members/{link}/"),
            {"valid_until": str(today())},
            content_type=JSON,
        )
        assert resp.status_code == 200
        # bis heute gilt noch; ein Tag später ist der Haushalt leer
        HouseholdMember.objects.filter(pk=link).update(
            valid_until=today() - datetime.timedelta(days=1)
        )
        assert c.get(hh_url(club)).json()[0]["members"] == []
        assert c.get(hh_url(club, hh["id"])).json()["members"][0]["current"] is False
        assert c.delete(hh_url(club, hh["id"])).status_code == 204
        stranger = make_user("fremd@example.org")
        assert api(stranger).get(hh_url(club)).status_code == 404

    def test_anderer_verein_abgelehnt(self, api, cal, board_a, family):
        c = api(board_a)
        hh = new_household(c, cal["a"])
        other = make_member(cal["b"], "Fremd", "Verein")
        resp = c.post(
            hh_url(cal["a"], hh["id"], "members/"), {"membership": other.pk}, content_type=JSON
        )
        assert resp.status_code == 404

    def test_austritt_beendet_und_loeschen_entfernt(self, api, cal, board_a, family):
        c = api(board_a)
        club = cal["a"]
        hh = new_household(c, club)
        start = today() - datetime.timedelta(days=10)
        assert add(c, club, hh, family["otto"], valid_from=str(start)).status_code == 201
        exit_date = today() - datetime.timedelta(days=3)
        exit_membership(family["otto"], exit_date, "exit")
        assert HouseholdMember.objects.get().valid_until == exit_date
        _purge_membership(Membership.objects.get(pk=family["otto"].pk))
        assert not HouseholdMember.objects.exists()
        assert not Household.objects.exists()

    def test_vorschlaege_gleiche_anschrift(self, api, cal, board_a, family):
        c = api(board_a)
        club = cal["a"]
        details = ContactDetails.objects.get(person=family["otto"].person)
        details.street = "Andere Str. 1"
        details.save()
        found = c.get(hh_url(club, suffix="suggestions/")).json()
        assert len(found) == 1
        assert {m["first_name"] for m in found[0]["members"]} == {"Erika", "Max", "Lisa"}
        hh = new_household(c, club)
        for key in ("erika", "max", "lisa"):
            add(c, club, hh, family[key])
        assert c.get(hh_url(club, suffix="suggestions/")).json() == []


class TestBriefname:
    def test_formen(self):
        assert letter_name([("", "Erika", "Muster", "weiblich")]) == "Erika Muster"
        two = [("", "Erika", "Muster", "weiblich"), ("", "Max", "Muster", "männlich")]
        assert letter_name(two) == "Familie Erika und Max Muster"
        four = two + [("", "Lisa", "Muster", ""), ("", "Tim", "Muster", "")]
        assert letter_name(four) == "Familie Muster"
        mixed = [("Dr.", "Erika", "Muster", "weiblich"), ("", "Max", "Beispiel", "männlich")]
        assert letter_name(mixed) == "Frau Dr. Erika Muster und Herrn Max Beispiel"


class TestRundschreiben:
    def _household(self, api, cal, board_a, family):
        c = api(board_a)
        club = cal["a"]
        hh = new_household(c, club)
        add(c, club, hh, family["erika"], role="adult")
        add(c, club, hh, family["max"], role="adult")
        add(c, club, hh, family["lisa"], role="child")
        return c, club

    def test_ein_brief_und_eine_mail_je_haushalt(self, api, cal, board_a, family):
        c, club = self._household(api, cal, board_a, family)
        without_email(family["erika"])
        without_email(family["max"])
        url = base(club)
        data = draft(c, url, body="{Anrede},\n\nHallo {Vorname} aus {Haushalt}")
        result = preview(c, url, data["id"])
        rows = {i["first_name"]: i for i in result["items"]}
        # Erika und Max: ein Brief (Erika, Erwachsene zuerst); Lisa teilt keine Adresse mehr
        assert rows["Erika"]["channel"] == "letter"
        assert rows["Max"]["channel"] is None and rows["Max"]["merged_into"] == rows["Erika"]["key"]
        assert rows["Lisa"]["channel"] == "mail"
        assert rows["Otto"]["channel"] == "mail"
        assert result["counts"]["letter"] == 1 and result["counts"]["merged"] == 1
        # Ausschalten: wieder je Person
        c.patch(f"{url}{data['id']}/", {"filters": {"households_merge": False}}, content_type=JSON)
        result = preview(c, url, data["id"])
        assert result["counts"]["letter"] == 2 and result["counts"]["merged"] == 0

    def test_versand_brief_mit_familienanschrift(
        self, api, cal, board_a, family, settings, django_capture_on_commit_callbacks
    ):
        c, club = self._household(api, cal, board_a, family)
        without_email(family["erika"])
        without_email(family["max"])
        url = base(club)
        data = draft(c, url, body="{Anrede},\n\nHallo {Vorname}")
        send(c, url, data["id"], django_capture_on_commit_callbacks, settings)
        letter = CircularRecipient.objects.get(channel="letter")
        assert letter.address.splitlines()[0] == "Familie Erika und Max Muster"
        assert letter.values["Anrede"] == "Sehr geehrte Familie Muster"
        assert letter.values["Vorname"] == "Erika und Max"
        assert letter.values["Haushalt"] == "Familie Muster"
        # Mail an die gemeinsame Adresse: Erika fehlt (Brief), Lisa bekommt ihre eigene
        assert CircularRecipient.objects.filter(channel="mail").count() == 2

    def test_gemeinsame_mailadresse(self, api, cal, board_a, family):
        c, club = self._household(api, cal, board_a, family)
        url = base(club)
        data = draft(c, url)
        rows = {i["first_name"]: i for i in preview(c, url, data["id"])["items"]}
        # Erika und Lisa haben dieselbe Adresse: eine Mail; Max seine eigene
        assert rows["Erika"]["channel"] == "mail"
        assert rows["Lisa"]["merged_into"] == rows["Erika"]["key"]
        assert rows["Max"]["channel"] == "mail"

    def test_nicht_bei_personlichen_platzhaltern(self, api, cal, board_a, family):
        c, club = self._household(api, cal, board_a, family)
        url = base(club)
        data = draft(c, url, body="{Mitgliedsjahre} Jahre")
        result = preview(c, url, data["id"])
        assert result["counts"]["merged"] == 0
