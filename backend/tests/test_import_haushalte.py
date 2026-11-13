"""Haushalte und Firmen im Excel-Import und -Export der Mitglieder (H6). Alles erfunden."""

import io

import pytest
from openpyxl import load_workbook

from core.tenancy import tenant_context
from members.models import Household, HouseholdMember

from .test_import_organisationen import ADDRESS, run_import
from .test_m2_members import make_types

pytestmark = pytest.mark.django_db
JSON = "application/json"

HEADER = [
    "Typ",
    "Name",
    "Vorname",
    "Geburtsdatum",
    "Straße",
    "PLZ",
    "Ort",
    "Art",
    "Eintritt",
    "Mitgliedsnummer",
    "Haushalt",
    "Rolle im Haushalt",
    "Firma",
    "Beitrag über",
]


@pytest.fixture(autouse=True)
def _eager(settings, tmp_path):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.PRIVATE_ROOT = tmp_path / "private"


@pytest.fixture
def types(orgs):
    return make_types(orgs["a"])


def person(last, first, birth, number, *household):
    return ["Person", last, first, birth, *ADDRESS, number, *household]


def test_spalten_werden_erkannt(api, orgs, types, board_a):
    from .test_m5_exchange import upload

    job = upload(api(board_a), orgs["a"], [HEADER]).json()
    mapped = [job["mapping"].get(str(i)) for i in range(10, len(HEADER))]
    assert mapped == ["household", "household_role", "company", "fee_via"]


def test_import_export_und_rueckgaengig(api, orgs, types, board_a):
    c = api(board_a)
    org = orgs["a"]
    data = [
        HEADER,
        person("Muster", "Erika", "01.01.1980", "7", "Familie Muster", "Erwachsener", "", ""),
        person("Muster", "Lisa", "01.01.2012", "8", "familie muster", "Kind", "", "Haushalt"),
        person("Beispiel", "Ina", "01.01.1990", "9", "", "", "Musterbau GmbH", "Firma"),
        person("Ohne", "Anna", "01.01.1991", "10", "", "", "", ""),
    ]
    job, checked = run_import(c, org, types, data)
    assert checked["counts"]["errors"] == 0, checked["preview"]
    done = c.post(f"/api/orgs/{org.pk}/imports/{job['id']}/run/").json()
    assert done["status"] == "imported", done
    with tenant_context(org.pk):
        family = Household.objects.get(kind="family")
        assert family.name == "Familie Muster"
        links = {
            link.membership.club_number: link
            for link in HouseholdMember.objects.select_related("membership")
        }
        assert set(links) == {"7", "8", "9"}
        assert (links["7"].role, links["7"].pays_via) == ("adult", False)
        assert (links["8"].role, links["8"].pays_via) == ("child", True)
        assert links["9"].household.kind == "company" and links["9"].pays_via

    resp = c.post(
        f"/api/orgs/{org.pk}/exports/",
        {
            "kind": "members",
            "file_format": "xlsx",
            "columns": ["club_number", "household", "household_role", "company", "fee_via"],
        },
        content_type=JSON,
    )
    assert resp.status_code == 201, resp.json()
    file = c.get(f"/api/orgs/{org.pk}/exports/{resp.json()['id']}/download/")
    ws = load_workbook(io.BytesIO(b"".join(file.streaming_content))).worksheets[0]
    assert [x.value for x in ws[1]][1:] == [
        "Haushalt",
        "Rolle im Haushalt",
        "Firma",
        "Beitrag über",
    ]
    rows = {str(r[0].value): [x.value or "" for x in r[1:]] for r in ws.iter_rows(min_row=2)}
    assert rows["8"] == ["Familie Muster", "Kind", "", "Haushalt"]
    assert rows["9"] == ["", "", "Musterbau GmbH", "Firma"]
    assert rows["10"] == ["", "", "", ""]

    assert c.post(f"/api/orgs/{org.pk}/imports/{job['id']}/undo/").status_code == 200
    with tenant_context(org.pk):
        assert not Household.objects.exists()


@pytest.mark.parametrize(
    "household,expected",
    [
        (["Familie Muster", "Oma", "", ""], "Rolle im Haushalt"),
        (["", "", "", "Firma"], "Spalte „Firma“ ist leer"),
        (["Familie Muster", "", "", "Verein"], "Beitrag über"),
    ],
)
def test_ungueltige_angaben(api, orgs, types, board_a, household, expected):
    c = api(board_a)
    data = [HEADER, person("Muster", "Erika", "01.01.1980", "7", *household)]
    _, checked = run_import(c, orgs["a"], types, data)
    assert checked["counts"]["errors"] == 1
    assert expected in " ".join(checked["preview"][0]["messages"])
