"""Zusatzfelder für Geschäftspartner: Felder anlegen, Werte pflegen, Rechte, Löschen,
Zusammenführen, Excel und Mandantentrennung."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import load_workbook

from billing.models import PartnerField, PartnerFieldValue
from core.tenancy import tenant_context

from .factories import give_role, make_user
from .test_rls import as_app_role

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture
def club(orgs):
    return orgs["a"]


@pytest.fixture
def base(club):
    return f"/api/orgs/{club.pk}/billing/"


@pytest.fixture
def c(api, board_a):
    return api(board_a)


def partner(c, base, name="Getränke Beispiel GmbH"):
    response = c.post(f"{base}partners/", {"details": {"name": name}}, content_type=JSON)
    assert response.status_code == 201, response.content
    return response.json()


def field(c, base, **data):
    response = c.post(f"{base}partner-fields/", data, content_type=JSON)
    assert response.status_code == 201, response.content
    return response.json()


def test_felder_anlegen_und_werte_pflegen(c, base):
    since = field(c, base, label="Kunde seit", field_type="yearrange")
    level = field(c, base, label="Sponsorstufe", field_type="choice", choices=["Gold", "Silber"])
    events = field(
        c,
        base,
        label="Veranstaltungen",
        repeatable=True,
        subfields=[{"label": "Anlass", "type": "text"}, {"label": "Datum", "type": "date"}],
    )
    assert level["key"] == "sponsorstufe" and level["federation_wide"] is False
    p = partner(c, base)
    path = f"{base}partners/{p['id']}/fields/"
    rows = c.get(path).json()
    assert [r["definition"]["label"] for r in rows] == [
        "Kunde seit",
        "Sponsorstufe",
        "Veranstaltungen",
    ]
    bad = c.put(path, {"values": {str(level["id"]): "Bronze"}}, content_type=JSON)
    assert bad.status_code == 400 and str(level["id"]) in bad.json()
    saved = c.put(
        path,
        {
            "values": {
                str(since["id"]): "2019",
                str(level["id"]): "Gold",
                str(events["id"]): [{"anlass": "Schützenfest", "datum": "2026-07-04"}],
            }
        },
        content_type=JSON,
    )
    assert saved.status_code == 200, saved.content
    values = {r["definition"]["label"]: r["value"] for r in saved.json()}
    assert values["Kunde seit"] == "2019" and values["Sponsorstufe"] == "Gold"
    assert values["Veranstaltungen"] == [{"anlass": "Schützenfest", "datum": "2026-07-04"}]
    # Archivierte Felder verschwinden aus der Akte, die Werte bleiben
    assert c.post(f"{base}partner-fields/{level['id']}/archive/").status_code == 200
    assert len(c.get(path).json()) == 2
    # Ein ausgefülltes Feld lässt sich nur ausdrücklich samt Werten löschen
    assert c.delete(f"{base}partner-fields/{since['id']}/").status_code == 409
    assert c.delete(f"{base}partner-fields/{since['id']}/?mit_werten=1").status_code == 204


def test_rechte(api, club, base, c):
    p = partner(c, base)
    user = make_user("fest@example.org")
    give_role(user, club, ["partners.view", "partners.edit"], name="Festausschuss")
    other = api(user)
    made = field(other, base, label="Lieferzeit", field_type="text")
    assert (
        other.put(
            f"{base}partners/{p['id']}/fields/",
            {"values": {str(made["id"]): "2 Tage"}},
            content_type=JSON,
        ).json()[0]["value"]
        == "2 Tage"
    )
    reader = make_user("lesen@example.org")
    give_role(reader, club, ["partners.view"], name="Nur lesen")
    readonly = api(reader)
    assert readonly.get(f"{base}partner-fields/").status_code == 200
    assert (
        readonly.post(f"{base}partner-fields/", {"label": "X"}, content_type=JSON).status_code
        == 403
    )
    nobody = make_user("mitglied@example.org")
    give_role(nobody, club, ["events.view"], name="Mitglied")
    assert api(nobody).get(f"{base}partner-fields/").status_code == 403


def test_zusammenfuehren_nimmt_werte_mit(c, base, club):
    note = field(c, base, label="Lieferzeit", field_type="text")
    level = field(c, base, label="Stufe", field_type="text")
    keep, other = partner(c, base, "Bleibt"), partner(c, base, "Doppelt")
    c.put(
        f"{base}partners/{keep['id']}/fields/",
        {"values": {str(note["id"]): "1 Tag"}},
        content_type=JSON,
    )
    c.put(
        f"{base}partners/{other['id']}/fields/",
        {"values": {str(note["id"]): "3 Tage", str(level["id"]): "Gold"}},
        content_type=JSON,
    )
    response = c.post(
        f"{base}partners/{keep['id']}/merge/", {"other": other["id"]}, content_type=JSON
    )
    assert response.status_code == 200, response.content
    values = {
        r["definition"]["label"]: r["value"]
        for r in c.get(f"{base}partners/{keep['id']}/fields/").json()
    }
    assert values == {"Lieferzeit": "1 Tag", "Stufe": "Gold"}


def test_excel_mit_zusatzfeldern(c, base):
    level = field(c, base, label="Sponsorstufe", field_type="choice", choices=["Gold", "Silber"])
    flag = field(c, base, label="Rahmenvertrag", field_type="bool")
    field(c, base, label="Liste", repeatable=True, subfields=[{"label": "A", "type": "text"}])
    p = partner(c, base)
    c.put(
        f"{base}partners/{p['id']}/fields/",
        {"values": {str(level["id"]): "Silber", str(flag["id"]): True}},
        content_type=JSON,
    )
    book = load_workbook(io.BytesIO(c.get(f"{base}partners/export/").content))
    sheet = book.worksheets[0]
    head = [cell.value for cell in sheet[1]]
    assert "Liste" not in head
    row = {h: cell.value for h, cell in zip(head, sheet[2], strict=True)}
    assert row["Sponsorstufe"] == "Silber" and row["Rahmenvertrag"] == "Ja"
    sheet.cell(2, head.index("Sponsorstufe") + 1, "Gold")
    sheet.cell(2, head.index("Rahmenvertrag") + 1, "Nein")
    sheet.append(["", "Neuer Partner"] + [""] * (len(head) - 2))
    sheet.cell(3, head.index("Sponsorstufe") + 1, "Platin")
    out = io.BytesIO()
    book.save(out)
    result = c.post(
        f"{base}partners/import/", {"file": SimpleUploadedFile("p.xlsx", out.getvalue())}
    ).json()
    assert result["updated"] == 1 and result["created"] == 0, result
    assert len(result["errors"]) == 1 and "Sponsorstufe" in result["errors"][0]
    values = {
        r["definition"]["label"]: r["value"]
        for r in c.get(f"{base}partners/{p['id']}/fields/").json()
    }
    assert values["Sponsorstufe"] == "Gold" and values["Rahmenvertrag"] is False
    assert len(c.get(f"{base}partners/").json()) == 1


def test_fremder_verein_sieht_nichts(c, base, orgs):
    made = field(c, base, label="Lieferzeit", field_type="text")
    p = partner(c, base)
    c.put(
        f"{base}partners/{p['id']}/fields/",
        {"values": {str(made["id"]): "1 Tag"}},
        content_type=JSON,
    )
    with as_app_role(), tenant_context(orgs["b"].pk):
        assert not PartnerField.objects.exists()
        assert not PartnerFieldValue.objects.exists()
    foreign = f"/api/orgs/{orgs['b'].pk}/billing/partners/{p['id']}/fields/"
    assert c.get(foreign).status_code in (403, 404)
