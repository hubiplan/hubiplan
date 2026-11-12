"""Titel (Dr., Prof. …) als festes Feld der Person: Akte, Anrede, Anschrift, Import/Export,
Übernahme aus einem Zusatzfeld (Ralf 12.11.: Auswahlliste oder frei). Alles erfunden."""

import io

import pytest
from django.core.management import call_command
from openpyxl import load_workbook

from billing.services import member_recipient
from circulars import recipients as rcp
from circulars.models import Circular
from circulars.recipients import Candidate, address_of, formal_salutation, informal_salutation
from core.tenancy import tenant_context
from customfields.models import FieldDefinition, FieldValue
from members.models import ContactPerson, Membership, Person, with_title
from members.title import parse_title, take_over_field

from .test_m2_members import admit, make_types
from .test_m5_exchange import upload
from .test_organisationsmitglieder import admit_org

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture(autouse=True)
def _eager(settings, tmp_path):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.PRIVATE_ROOT = tmp_path / "private"


@pytest.fixture
def types(orgs):
    return {key: make_types(orgs[key]) for key in ("a", "b")}


def detail_url(org, pk):
    return f"/api/orgs/{org.pk}/members/{pk}/"


class TestErkennen:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Dr.", "Dr."),
            ("dr", "Dr."),
            (" Dr.  med. ", "Dr. med."),
            ("Dr. Dr.", "Dr. Dr."),
            ("Prof.", "Prof."),
            ("Professor", "Prof."),
            ("Prof. Dr.", "Prof. Dr."),
            ("prof.dr.", "Prof. Dr."),
            ("", ""),
            (None, ""),
            ("-", ""),
            # frei: unbekannte Titel bleiben, wie sie eingegeben wurden
            ("Dipl.-Ing.", "Dipl.-Ing."),
            ("  Dr.  h. c. ", "Dr. h. c."),
        ],
    )
    def test_schreibweisen(self, raw, expected):
        assert parse_title(raw) == expected

    def test_zu_lang_wird_gekuerzt(self):
        assert len(parse_title("X" * 50)) == 30

    def test_name_mit_titel(self):
        assert with_title("Dr.", "Max", "Muster") == "Dr. Max Muster"
        assert with_title("", "Max", "Muster") == "Max Muster"
        assert with_title("Prof.", "", "Muster") == "Prof. Muster"


class TestAkte:
    def test_aufnahme_und_aendern(self, api, orgs, types, board_a):
        c = api(board_a)
        resp = admit(c, orgs["a"], types["a"]["aktiv"], title="dr")
        assert resp.status_code == 201, resp.json()
        data = resp.json()
        assert data["title"] == "Dr."
        assert Person.objects.get().title == "Dr."

        resp = c.patch(detail_url(orgs["a"], data["id"]), {"title": "Prof. Dr."}, content_type=JSON)
        assert resp.status_code == 200, resp.json()
        assert resp.json()["title"] == "Prof. Dr."

        resp = c.patch(
            detail_url(orgs["a"], data["id"]), {"title": "Dipl.-Ing."}, content_type=JSON
        )
        assert resp.status_code == 200, resp.json()
        assert resp.json()["title"] == "Dipl.-Ing."

        resp = c.patch(detail_url(orgs["a"], data["id"]), {"title": ""}, content_type=JSON)
        assert resp.status_code == 200
        assert Person.objects.get().title == ""

    def test_zu_lang(self, api, orgs, types, board_a):
        c = api(board_a)
        data = admit(c, orgs["a"], types["a"]["aktiv"]).json()
        assert data["title"] == ""
        resp = c.patch(detail_url(orgs["a"], data["id"]), {"title": "X" * 31}, content_type=JSON)
        assert resp.status_code == 400
        assert "title" in resp.json()

    def test_organisation_ohne_titel(self, api, orgs, types, board_a):
        resp = admit_org(api(board_a), orgs["a"], types["a"]["foerder"], title="Dr.")
        assert resp.status_code == 201, resp.json()
        assert Person.objects.get().title == ""

    def test_liste_und_export(self, api, orgs, types, board_a):
        c = api(board_a)
        admit(c, orgs["a"], types["a"]["aktiv"], last_name="Adler", title="Prof.")
        rows = c.get(f"/api/orgs/{orgs['a'].pk}/members/").json()["results"]
        assert [r["title"] for r in rows] == ["Prof."]
        resp = c.post(
            f"/api/orgs/{orgs['a'].pk}/exports/",
            {"kind": "members", "file_format": "xlsx", "columns": ["last_name", "title"]},
            content_type=JSON,
        )
        assert resp.status_code == 201, resp.json()
        job = c.get(f"/api/orgs/{orgs['a'].pk}/exports/{resp.json()['id']}/").json()
        file = c.get(f"/api/orgs/{orgs['a'].pk}/exports/{job['id']}/download/")
        ws = load_workbook(io.BytesIO(b"".join(file.streaming_content))).active
        assert [x.value for x in ws[1]] == ["Name", "Titel"]
        assert ws["B2"].value == "Prof."


class TestAnrede:
    def candidate(self, gender, title="Dr."):
        return Candidate(
            key="m1", club=None, first_name="Max", last_name="Muster", gender=gender, title=title
        )

    def test_foermlich_mit_titel(self):
        assert formal_salutation(self.candidate("männlich")) == "Sehr geehrter Herr Dr. Muster"
        assert (
            formal_salutation(self.candidate("weiblich", "Prof. Dr."))
            == "Sehr geehrte Frau Prof. Dr. Muster"
        )
        assert formal_salutation(self.candidate("")) == "Guten Tag Dr. Max Muster"
        assert formal_salutation(self.candidate("männlich", "")) == "Sehr geehrter Herr Muster"

    def test_du_ohne_titel(self):
        assert informal_salutation(self.candidate("männlich")) == "Lieber Max"

    def test_anschrift(self):
        row = {"street": "Lindenweg 4", "postal_code": "12345", "city": "Musterstadt"}
        assert address_of("Max", "Muster", row, "Dr.") == (
            "Dr. Max Muster\nLindenweg 4\n12345 Musterstadt"
        )
        assert address_of("Max", "Muster", row).startswith("Max Muster\n")


class TestPostUndRechnung:
    def test_rundschreiben_an_mitglied(self, api, orgs, types, board_a):
        admit(api(board_a), orgs["a"], types["a"]["aktiv"], gender="weiblich", title="Dr.")
        org = orgs["a"]
        with tenant_context(org.pk):
            circular = Circular.objects.create(organization=org, subject="Info", body="{Anrede}")
            selection = rcp.select(circular)
            rcp.fill_values(circular, selection, {"Anrede"})
        (row,) = [c for c in selection.candidates if c.last_name == "Muster"]
        assert row.values["Anrede"] == "Sehr geehrte Frau Dr. Muster"
        assert row.address.startswith("Dr. Erika Muster\n")

    def test_rechnung_an_mitglied(self, api, orgs, types, board_a):
        data = admit(api(board_a), orgs["a"], types["a"]["aktiv"], title="Prof.").json()
        org = orgs["a"]
        with tenant_context(org.pk):
            membership = Membership.objects.get(pk=data["id"])
            assert member_recipient(org, membership)["recipient_name"] == "Prof. Erika Muster"

    def test_zhd_ansprechpartner_mit_titel(self, api, orgs, types, board_a):
        resp = admit_org(api(board_a), orgs["a"], types["a"]["foerder"])
        org = orgs["a"]
        with tenant_context(org.pk):
            firma = Membership.objects.get(pk=resp.json()["id"])
            ContactPerson.objects.create(
                organization=org,
                membership=firma,
                last_name="Kasse",
                first_name="Karla",
                title="Dr.",
                email="kasse@musterbau.example",
                is_primary=True,
            )
            name = member_recipient(org, firma)["recipient_name"]
        assert name.endswith("\nz. Hd. Dr. Karla Kasse")

    def test_ansprechpartner_ueber_schnittstelle(self, api, orgs, types, board_a):
        c = api(board_a)
        firma = admit_org(c, orgs["a"], types["a"]["foerder"]).json()
        resp = c.post(
            f"/api/orgs/{orgs['a'].pk}/members/{firma['id']}/contacts/",
            {"last_name": "Kasse", "first_name": "Karla", "title": "prof"},
            content_type=JSON,
        )
        assert resp.status_code == 201, resp.json()
        assert resp.json()["title"] == "Prof."


HEADER = ["Nachname", "Vorname", "Geburtsdatum", "Titel", "Straße", "PLZ", "Ort", "Art"]
HEADER += ["Eintritt"]


class TestImport:
    def test_titel_wird_erkannt(self, api, orgs, types, board_a):
        c = api(board_a)
        org = orgs["a"]
        # Ein gleichnamiges Zusatzfeld darf das feste Feld nicht verdrängen
        FieldDefinition.objects.create(organization=org, label="Titel", key="titel")
        data = [HEADER]
        for i, title in enumerate(["dr", "Prof. Dr.", "Dipl.-Ing.", ""]):
            data.append(
                [f"Person{i}", "Test", f"0{i + 1}.01.1990", title, "Weg 1", "12345", "Stadt"]
                + ["Akt.", "01.03.2015"]
            )
        job = upload(c, org, data).json()
        assert job["mapping"]["3"] == "title"
        resp = c.patch(
            f"/api/orgs/{org.pk}/imports/{job['id']}/",
            {
                "mapping": job["mapping"],
                "value_mapping": {"member_type": {"Akt.": str(types["a"]["aktiv"].pk)}},
            },
            content_type=JSON,
        )
        assert resp.status_code == 200, resp.json()
        checked = c.post(f"/api/orgs/{org.pk}/imports/{job['id']}/validate/").json()
        assert checked["counts"]["errors"] == 0, checked
        done = c.post(f"/api/orgs/{org.pk}/imports/{job['id']}/run/").json()
        assert done["status"] == "imported", done
        titles = dict(Person.objects.values_list("last_name", "title"))
        assert titles == {
            "Person0": "Dr.",
            "Person1": "Prof. Dr.",
            "Person2": "Dipl.-Ing.",
            "Person3": "",
        }


class TestUebernahmeAusZusatzfeld:
    def make_field_values(self, orgs, values):
        org = orgs["a"]
        definition = FieldDefinition.objects.create(organization=org, label="Titel", key="titel")
        persons = []
        with tenant_context(org.pk):
            for i, value in enumerate(values):
                p = Person.objects.create(
                    scope=orgs["federation"],
                    last_name=f"P{i}",
                    first_name="Test",
                    birth_date="1990-01-01",
                )
                FieldValue.objects.create(
                    organization=org, definition=definition, person=p, value=value
                )
                persons.append(p)
        return definition, persons

    def test_werte_werden_uebernommen(self, orgs):
        definition, persons = self.make_field_values(orgs, ["Dr.", "prof", "Dipl.-Ing.", "", None])
        # Vorhandener Titel bleibt
        Person.objects.filter(pk=persons[2].pk).update(title="Dr.")
        count = take_over_field(Person, FieldDefinition, FieldValue)
        assert count == 2
        titles = [Person.objects.get(pk=p.pk).title for p in persons]
        assert titles == ["Dr.", "Prof.", "Dr.", "", ""]
        assert FieldValue.objects.filter(definition=definition).count() == 5

    def test_befehl(self, orgs, capsys):
        self.make_field_values(orgs, ["Dr."])
        call_command("titel_uebernehmen")
        assert "1 Personen" in capsys.readouterr().out
        assert Person.objects.get().title == "Dr."
