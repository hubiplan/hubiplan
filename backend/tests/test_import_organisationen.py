"""Excel-Import und -Export mit Organisationsmitgliedern (Konzept juristische Personen, J6)."""

import io

import pytest
from openpyxl import load_workbook

from exchange.importer import parse_legal_form
from members.models import ContactPerson, LegalForm, Person

from .test_m2_members import make_types
from .test_m5_exchange import upload
from .test_organisationsmitglieder import admit_org

pytestmark = pytest.mark.django_db
JSON = "application/json"

HEADER = [
    "Typ",
    "Name",
    "Namenszusatz",
    "Rechtsform",
    "Vorname",
    "Geburtsdatum",
    "Straße",
    "PLZ",
    "Ort",
    "Art",
    "Eintritt",
    "Mitgliedsnummer",
    "Ansprechpartner Name",
    "Ansprechpartner Vorname",
    "Ansprechpartner Funktion",
    "Ansprechpartner E-Mail",
]
ADDRESS = ["Musterstraße 1", "12345", "Musterstadt", "Akt.", "01.03.2015"]


@pytest.fixture(autouse=True)
def _eager(settings, tmp_path):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.PRIVATE_ROOT = tmp_path / "private"


@pytest.fixture
def types(orgs):
    return make_types(orgs["a"])


def run_import(c, org, types, data):
    job = upload(c, org, data).json()
    resp = c.patch(
        f"/api/orgs/{org.pk}/imports/{job['id']}/",
        {
            "mapping": job["mapping"],
            "value_mapping": {"member_type": {"Akt.": str(types["aktiv"].pk)}},
        },
        content_type=JSON,
    )
    assert resp.status_code == 200, resp.json()
    checked = c.post(f"/api/orgs/{org.pk}/imports/{job['id']}/validate/").json()
    return job, checked


def test_spalten_werden_erkannt(api, orgs, types, board_a):
    job = upload(api(board_a), orgs["a"], [HEADER]).json()
    assert [job["mapping"][str(i)] for i in (0, 2, 3, 12, 13, 14, 15)] == [
        "kind",
        "name_suffix",
        "legal_form",
        "contact_last_name",
        "contact_first_name",
        "contact_function",
        "contact_email",
    ]


def test_organisation_mit_zwei_ansprechpartnern(api, orgs, types, board_a):
    c = api(board_a)
    org = orgs["a"]
    data = [
        HEADER,
        ["Organisation", "Musterbau", "Niederlassung Nord", "GmbH", "", "", *ADDRESS, "7"]
        + ["Muster", "Max", "Geschäftsführer", "max@musterbau.example"],
        ["Organisation", "Musterbau", "Niederlassung Nord", "GmbH", "", "", *ADDRESS, "7"]
        + ["Beispiel", "Eva", "Buchhaltung", "eva@musterbau.example"],
        ["Person", "Muster", "", "", "Erika", "01.01.1990", *ADDRESS, "8", "", "", "", ""],
    ]
    job, checked = run_import(c, org, types, data)
    assert checked["counts"]["errors"] == 0, checked["preview"]
    kinds = sorted((p["kind"], p["name"]) for p in checked["preview"])
    assert kinds == [
        ("organization", "Musterbau – Niederlassung Nord"),
        ("person", "Muster, Erika"),
    ]
    done = c.post(f"/api/orgs/{org.pk}/imports/{job['id']}/run/").json()
    assert done["status"] == "imported", done
    firma = Person.objects.get(kind="organization")
    assert firma.birth_date is None and firma.first_name == ""
    assert firma.legal_form == LegalForm.GMBH and firma.name_suffix == "Niederlassung Nord"
    contacts = ContactPerson.objects.order_by("pk")
    assert [(c.last_name, c.function, c.is_primary) for c in contacts] == [
        ("Muster", "Geschäftsführer", True),
        ("Beispiel", "Buchhaltung", False),
    ]
    # Rückgängig nimmt die Ansprechpartner mit
    assert c.post(f"/api/orgs/{org.pk}/imports/{job['id']}/undo/").status_code == 200
    assert not ContactPerson.objects.exists()


def test_organisationsname_ohne_typ_wird_nicht_geraten(api, orgs, types, board_a):
    c = api(board_a)
    data = [HEADER, ["", "Musterbau GmbH", "", "", "", "", *ADDRESS, "", "", "", "", ""]]
    _, checked = run_import(c, orgs["a"], types, data)
    assert checked["counts"]["errors"] == 1
    assert "Typ" in " ".join(checked["preview"][0]["messages"])


def test_ansprechpartner_nur_bei_organisationen(api, orgs, types, board_a):
    c = api(board_a)
    data = [
        HEADER,
        ["Person", "Muster", "", "", "Erika", "01.01.1990", *ADDRESS, ""]
        + ["Muster", "Max", "", ""],
    ]
    _, checked = run_import(c, orgs["a"], types, data)
    assert checked["counts"]["errors"] == 1


def test_organisation_schon_mitglied(api, orgs, types, board_a):
    c = api(board_a)
    admit_org(c, orgs["a"], types["foerder"], last_name="Musterbau", name_suffix="")
    data = [HEADER, ["Organisation", "Musterbau", "", "", "", "", *ADDRESS, "", "", "", "", ""]]
    _, checked = run_import(c, orgs["a"], types, data)
    assert checked["counts"]["errors"] == 1
    assert "bereits Mitglied" in " ".join(checked["preview"][0]["messages"])


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("GmbH", ("gmbh", "")),
        ("e. V.", ("ev", "")),
        ("GmbH & Co. KG", ("kg", "")),
        ("Anstalt des öffentlichen Rechts", ("other", "Anstalt des öffentlichen Rechts")),
        ("", ("", "")),
    ],
)
def test_rechtsform_lesen(raw, expected):
    assert parse_legal_form(raw) == expected


def test_excel_export_mit_ansprechpartnern(api, orgs, types, board_a):
    c = api(board_a)
    org = orgs["a"]
    firma = admit_org(c, org, types["foerder"]).json()
    c.post(
        f"/api/orgs/{org.pk}/members/{firma['id']}/contacts/",
        {"last_name": "Muster", "first_name": "Max", "email": "max@musterbau.example"},
        content_type=JSON,
    )
    resp = c.post(
        f"/api/orgs/{org.pk}/exports/",
        {
            "kind": "members",
            "file_format": "xlsx",
            "columns": ["kind", "last_name", "name_suffix", "legal_form", "contact_name"],
        },
        content_type=JSON,
    )
    assert resp.status_code == 201, resp.json()
    file = c.get(f"/api/orgs/{org.pk}/exports/{resp.json()['id']}/download/")
    wb = load_workbook(io.BytesIO(b"".join(file.streaming_content)))
    ws = wb.worksheets[0]
    assert [x.value for x in ws[2]] == [
        "Organisation",
        "Musterbau GmbH",
        "Niederlassung Musterstadt",
        "GmbH",
        "Max Muster",
    ]
    sheet = wb["Ansprechpartner"]
    assert sheet["C2"].value == "Max Muster" and sheet["E2"].value == "max@musterbau.example"
    assert sheet["G2"].value == "ja"
