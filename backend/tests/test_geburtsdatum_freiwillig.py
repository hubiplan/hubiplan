"""Geburtsdatum ist für Personen freiwillig (Aufnahme, Akte, Import, Beitrag, Geburtstage)."""

import datetime
import io
from decimal import Decimal

import pytest
from django.core.management import call_command

from billing.models import AgeRate, FeeRate
from billing.services import yearly_fee
from core.tenancy import rls_bypass
from members import personmarks, services
from members.models import Person

from .test_m2_members import admit, make_types
from .test_m5_exchange import upload

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture(autouse=True)
def _eager(settings, tmp_path):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.PRIVATE_ROOT = tmp_path / "private"


@pytest.fixture
def types(orgs):
    return make_types(orgs["a"])


def member_url(org, member, suffix=""):
    return f"/api/orgs/{org.pk}/members/{member['id']}/{suffix}"


class TestAufnahme:
    @pytest.mark.parametrize("value", ["", None])
    def test_ohne_geburtsdatum_aufnehmen(self, api, orgs, types, board_a, value):
        resp = admit(api(board_a), orgs["a"], types["aktiv"], birth_date=value)
        assert resp.status_code == 201, resp.json()
        assert resp.json()["birth_date"] is None
        person = Person.objects.get()
        assert person.birth_date is None
        assert person.marks_version == personmarks.VERSION
        assert person.last_birth_mark and person.first_birth_mark

    def test_feld_darf_fehlen(self, api, orgs, types, board_a):
        c = api(board_a)
        data = {
            "last_name": "Muster",
            "first_name": "Erika",
            "street": "Lindenweg 4",
            "postal_code": "12345",
            "city": "Musterstadt",
            "entry_date": "2015-03-01",
            "member_type": types["aktiv"].pk,
        }
        resp = c.post(f"/api/orgs/{orgs['a'].pk}/members/admit/", data, content_type=JSON)
        assert resp.status_code == 201, resp.json()

    def test_dublettensuche_ohne_datum_nur_eigene_mitglieder(
        self, api, orgs, types, board_a, board_b
    ):
        admit(api(board_a), orgs["a"], types["aktiv"], birth_date="")
        url = "/api/orgs/{}/members/duplicates/"
        params = {"name": "muster", "vorname": "ERIKA", "geburtsdatum": ""}
        own = api(board_a).get(url.format(orgs["a"].pk), params).json()
        assert [(d["last_name"], d["already_member_here"]) for d in own] == [("Muster", True)]
        # Anderer Verein im Verband: ohne Geburtsdatum keine Treffer
        assert api(board_b).get(url.format(orgs["b"].pk), params).json() == []

    def test_mit_datum_findet_person_ohne_datum_nicht(self, api, orgs, types, board_a):
        admit(api(board_a), orgs["a"], types["aktiv"], birth_date="")
        assert services.find_duplicates(orgs["b"], "Muster", "Erika", None) == []
        birth = datetime.date(1980, 5, 17)
        assert services.find_duplicates(orgs["b"], "Muster", "Erika", birth) == []


class TestAkte:
    def test_geburtsdatum_entfernen_und_nachtragen(self, api, orgs, types, board_a):
        c = api(board_a)
        m = admit(c, orgs["a"], types["aktiv"]).json()
        resp = c.patch(member_url(orgs["a"], m), {"birth_date": ""}, content_type=JSON)
        assert resp.status_code == 200, resp.json()
        assert resp.json()["birth_date"] is None
        person = Person.objects.get()
        assert person.birth_date is None and not person.birth_year_only
        resp = c.patch(member_url(orgs["a"], m), {"birth_date": "1981-02-03"}, content_type=JSON)
        assert resp.status_code == 200, resp.json()
        assert resp.json()["birth_date"] == "1981-02-03"

    def test_nur_jahr_wird_beim_entfernen_zurueckgesetzt(self, api, orgs, types, board_a):
        c = api(board_a)
        m = admit(c, orgs["a"], types["aktiv"]).json()
        with rls_bypass():
            person = Person.objects.get()
            person.birth_year_only = True
            person.save()
        resp = c.patch(member_url(orgs["a"], m), {"birth_date": None}, content_type=JSON)
        assert resp.status_code == 200, resp.json()
        with rls_bypass():
            person = Person.objects.get()
        assert person.birth_date is None and not person.birth_year_only
        assert person.last_year_mark == "" and person.first_year_mark == ""

    def test_geburtstage_ohne_datum_leer(self, api, orgs, types, board_a):
        c = api(board_a)
        admit(c, orgs["a"], types["aktiv"], birth_date="")
        data = c.get(
            f"/api/orgs/{orgs['a'].pk}/birthdays/", {"von": "2026-01-01", "bis": "2026-12-31"}
        ).json()
        assert data["results"] == []


class TestSuchmarken:
    def test_bestandslauf_meldet_person_ohne_datum_nicht_als_unlesbar(self, orgs):
        with rls_bypass():
            Person.objects.create(scope=orgs["federation"], last_name="Muster", first_name="Max")
        out = io.StringIO()
        call_command("personen_suchmarken", "--pruefen", stdout=out)
        assert "unlesbar: 0" in out.getvalue()


class TestBeitrag:
    def test_ohne_geburtsdatum_grundbeitrag(self, orgs, types):
        org = orgs["a"]
        FeeRate.objects.create(member_type=types["aktiv"], amount=Decimal("40"))
        AgeRate.objects.create(organization=org, name="Jugend", max_age=17, amount=Decimal("10"))
        assert yearly_fee(org, types["aktiv"], None, 2026) == (Decimal("40"), "")


class TestImport:
    HEADER = ["Name", "Vorname", "Straße", "PLZ", "Ort", "Art", "Eintritt"]
    ROW = ["Muster", "Erika", "Lindenweg 4", "12345", "Musterstadt", "Akt.", "01.03.2015"]

    def run(self, c, org, types, rows):
        job = upload(c, org, [self.HEADER, *rows]).json()
        resp = c.patch(
            f"/api/orgs/{org.pk}/imports/{job['id']}/",
            {
                "mapping": job["mapping"],
                "value_mapping": {"member_type": {"Akt.": str(types["aktiv"].pk)}},
            },
            content_type=JSON,
        )
        assert resp.status_code == 200, resp.json()
        checked = c.post(f"/api/orgs/{org.pk}/imports/{job['id']}/validate/")
        assert checked.status_code == 200, checked.json()
        return job, checked.json()

    def test_import_ohne_geburtsdatumsspalte(self, api, orgs, types, board_a):
        c = api(board_a)
        org = orgs["a"]
        job, checked = self.run(c, org, types, [self.ROW])
        assert checked["counts"]["errors"] == 0, checked["preview"]
        done = c.post(f"/api/orgs/{org.pk}/imports/{job['id']}/run/").json()
        assert done["status"] == "imported", done
        assert Person.objects.get().birth_date is None

    def test_gleicher_name_im_verein_wird_gemeldet(self, api, orgs, types, board_a):
        c = api(board_a)
        org = orgs["a"]
        admit(c, org, types["aktiv"], birth_date="")
        _, checked = self.run(c, org, types, [self.ROW])
        assert checked["counts"]["errors"] == 1, checked["preview"]
