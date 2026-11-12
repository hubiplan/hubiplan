"""Rechnungsanschrift im Excel-Import und -Export der Mitglieder (Ergänzung zu J3/J6)."""

import io

import pytest
from openpyxl import load_workbook

from exchange.export import billing_columns
from members.models import BillingAddress

from .test_import_organisationen import ADDRESS, run_import
from .test_m2_members import make_types
from .test_organisationsmitglieder import admit_org

pytestmark = pytest.mark.django_db
JSON = "application/json"

BILLING = [label for _, label, _ in billing_columns()]
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
    *BILLING,
]


@pytest.fixture(autouse=True)
def _eager(settings, tmp_path):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.PRIVATE_ROOT = tmp_path / "private"


@pytest.fixture
def types(orgs):
    return make_types(orgs["a"])


def billing(**values):
    order = [key for _, _, key in billing_columns()]
    return [values.get(key, "") for key in order]


def test_spalten_wie_im_export_werden_erkannt(api, orgs, types, board_a):
    from .test_m5_exchange import upload

    job = upload(api(board_a), orgs["a"], [HEADER]).json()
    mapped = [job["mapping"].get(str(i)) for i in range(10, len(HEADER))]
    assert mapped == [target for target, _, _ in billing_columns()]


def test_import_mit_rechnungsanschrift(api, orgs, types, board_a):
    c = api(board_a)
    org = orgs["a"]
    data = [
        HEADER,
        ["Organisation", "Musterbau GmbH", "", "", *ADDRESS, "7"]
        + billing(
            name="Musterbau GmbH Buchhaltung",
            attention="Kreditoren",
            street="Postfach 1234",
            postal_code="1234",
            city="Musterstadt",
            email="rechnung@musterbau.example",
            order_reference="B-42",
            leitweg_id="991-12345-67",
        ),
        # weitere Zeile derselben Organisation: gleiche Angaben sind kein Widerspruch
        ["Organisation", "Musterbau GmbH", "", "", *ADDRESS, "7"] + billing(city="Musterstadt"),
        ["Person", "Muster", "Erika", "01.01.2015", *ADDRESS, "8"]
        + billing(name="Max Muster", street="Elternweg 2", postal_code="54321", city="Beispielort"),
        ["Person", "Beispiel", "Eva", "01.01.1990", *ADDRESS, "9"]
        + billing(email="eva-rechnung@example.org"),
        ["Person", "Ohne", "Anna", "01.01.1991", *ADDRESS, "10"] + billing(),
    ]
    job, checked = run_import(c, org, types, data)
    assert checked["counts"]["errors"] == 0, checked["preview"]
    firma = next(p for p in checked["preview"] if p["kind"] == "organization")
    assert any("01234" in m for m in firma["messages"])  # führende 0 ergänzt
    done = c.post(f"/api/orgs/{org.pk}/imports/{job['id']}/run/").json()
    assert done["status"] == "imported", done

    by_number = {b.membership.club_number: b for b in BillingAddress.objects.all()}
    assert set(by_number) == {"7", "8", "9"}
    b = by_number["7"]
    assert (b.name, b.attention, b.street, b.postal_code, b.city) == (
        "Musterbau GmbH Buchhaltung",
        "Kreditoren",
        "Postfach 1234",
        "01234",
        "Musterstadt",
    )
    assert (b.email, b.order_reference, b.leitweg_id) == (
        "rechnung@musterbau.example",
        "B-42",
        "991-12345-67",
    )
    assert by_number["8"].has_address and by_number["8"].name == "Max Muster"
    assert not by_number["9"].has_address and by_number["9"].email == "eva-rechnung@example.org"

    # Rechnungen gehen an die Rechnungsanschrift
    from billing.services import member_recipient

    recipient = member_recipient(org, b.membership)
    assert recipient["recipient_name"] == "Musterbau GmbH Buchhaltung\nKreditoren"
    assert recipient["recipient_email"] == "rechnung@musterbau.example"

    # Rückgängig nimmt die Rechnungsanschriften mit
    assert c.post(f"/api/orgs/{org.pk}/imports/{job['id']}/undo/").status_code == 200
    assert not BillingAddress.objects.exists()


@pytest.mark.parametrize(
    "values,expected",
    [
        ({"street": "Postfach 1"}, "Straße (oder Postfach) und Ort"),
        ({"postal_code": "12345", "city": "Musterstadt"}, "Straße (oder Postfach) und Ort"),
        ({"email": "keine-mail"}, "Rechnungs-E-Mail ist ungültig"),
        ({"leitweg_id": "9" * 51}, "höchstens 50 Zeichen"),
    ],
)
def test_ungueltige_rechnungsanschrift(api, orgs, types, board_a, values, expected):
    c = api(board_a)
    data = [HEADER, ["Person", "Muster", "Erika", "01.01.1990", *ADDRESS, "8"] + billing(**values)]
    _, checked = run_import(c, orgs["a"], types, data)
    assert checked["counts"]["errors"] == 1
    assert expected in " ".join(checked["preview"][0]["messages"])


def test_widerspruechliche_rechnungsanschrift(api, orgs, types, board_a):
    c = api(board_a)
    row = ["Organisation", "Musterbau GmbH", "", "", *ADDRESS, "7"]
    data = [
        HEADER,
        row + billing(street="Postfach 1", city="Musterstadt"),
        row + billing(city="Beispielort"),
    ]
    _, checked = run_import(c, orgs["a"], types, data)
    assert checked["counts"]["errors"] == 1
    message = " ".join(checked["preview"][0]["messages"])
    assert "Rechnung Ort" in message and "widerspricht Zeile 2" in message


def test_export_mit_rechnungsanschrift(api, orgs, types, board_a):
    c = api(board_a)
    org = orgs["a"]
    firma = admit_org(c, org, types["foerder"]).json()
    resp = c.put(
        f"/api/orgs/{org.pk}/members/{firma['id']}/billing-address/",
        {
            "name": "Musterbau Buchhaltung",
            "street": "Postfach 1234",
            "postal_code": "12345",
            "city": "Musterstadt",
            "email": "rechnung@musterbau.example",
            "leitweg_id": "991-12345-67",
        },
        content_type=JSON,
    )
    assert resp.status_code == 200, resp.json()
    keys = [target for target, _, _ in billing_columns()]
    resp = c.post(
        f"/api/orgs/{org.pk}/exports/",
        {"kind": "members", "file_format": "xlsx", "columns": ["last_name", *keys]},
        content_type=JSON,
    )
    assert resp.status_code == 201, resp.json()
    file = c.get(f"/api/orgs/{org.pk}/exports/{resp.json()['id']}/download/")
    ws = load_workbook(io.BytesIO(b"".join(file.streaming_content))).worksheets[0]
    assert [x.value for x in ws[1]] == ["Name", *BILLING]
    values = [x.value or "" for x in ws[2]]
    assert values == [
        "Musterbau GmbH",
        "Musterbau Buchhaltung",
        "",
        "Postfach 1234",
        "12345",
        "Musterstadt",
        "",
        "rechnung@musterbau.example",
        "",
        "991-12345-67",
    ]
