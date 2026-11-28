# ruff: noqa: F811  (Fixtures als Parameter)
"""Gleichzeitiges Bearbeiten, dritte Runde (core/versioning.py): Veranstaltungen und Anlagen
der Kasse, Qualifikationen und frühere Amtsinhaber. Wer mit einer veralteten Fassung speichert
oder löscht, bekommt 409. Erfundene Daten."""

import pytest

from access.models import Role, RoleAssignment
from qualifications.models import Qualification

from .factories import make_member
from .test_qualifikationen import new_type, ok, records, setup  # noqa: F401  (Fixture)
from .test_veranstaltungen import _private, c, club, fest, fin  # noqa: F401  (Fixtures)

pytestmark = pytest.mark.django_db
JSON = "application/json"


def _stale(resp):
    assert resp.status_code == 409, resp.content
    assert "inzwischen geändert. Bitte neu laden." in resp.json()["detail"]


def test_veranstaltung_veraltete_fassung(c, fin, fest):
    one = f"{fin}/projects/{fest['id']}/"
    alt = fest["version"]

    resp = c.patch(one, {"name": "Schützenfest 2025 (Zelt)", "version": alt}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    assert resp.json()["version"] > alt

    _stale(c.patch(one, {"name": "Anders", "version": alt}, content_type=JSON))
    _stale(c.delete(one, {"version": alt}, content_type=JSON))
    assert c.get(one).json()["name"] == "Schützenfest 2025 (Zelt)"

    # Ohne Fassung (ältere Oberfläche) wie bisher
    assert c.patch(one, {"name": "Schützenfest 2025"}, content_type=JSON).status_code == 200


def test_anlage_veraltete_fassung(c, fin, club):
    club.enabled_modules = [*club.enabled_modules, "tax"]
    club.tax_areas_enabled = True
    club.save()
    made = c.post(
        f"{fin}/assets/",
        {
            "name": "Festzelt",
            "acquired_on": "2025-04-10",
            "cost": "12000.00",
            "method": "linear",
            "useful_life": 10,
            "tax_area": "business",
        },
        content_type=JSON,
    )
    assert made.status_code == 201, made.json()
    asset = made.json()
    one = f"{fin}/assets/{asset['id']}/"

    resp = c.patch(one, {"name": "Festzelt groß", "version": asset["version"]}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    _stale(c.patch(one, {"name": "Anders", "version": asset["version"]}, content_type=JSON))
    _stale(c.delete(one, {"version": asset["version"]}, content_type=JSON))
    assert c.get(one).json()["name"] == "Festzelt groß"


def test_qualifikation_veraltete_fassung(setup):
    s = setup
    kind = new_type(s, "Erste Hilfe", validity_months=24)
    anna = make_member(s["org"], "Anna", "Muster")
    url = records(s, anna)
    first = ok(s["c"].post(url, {"kind": kind["id"], "acquired_on": "2020-05-31"}, JSON))
    one = f"{url}{first['id']}/"
    alt = first["version"]

    resp = s["c"].patch(one, {"note": "Kurs beim DRK", "version": alt}, JSON)
    assert resp.status_code == 200, resp.content
    assert resp.json()["version"] > alt

    _stale(s["c"].patch(one, {"note": "Anders", "version": alt}, JSON))
    _stale(s["c"].delete(one, {"version": alt}, JSON))
    assert Qualification.objects.get(pk=first["id"]).note == "Kurs beim DRK"

    # Art: Ändern mit veralteter Fassung
    art = f"{s['types']}{kind['id']}/"
    assert (
        s["c"].patch(art, {"name": "Ersthelfer", "version": kind["version"]}, JSON).status_code
        == 200
    )
    _stale(s["c"].patch(art, {"name": "Anders", "version": kind["version"]}, JSON))


def test_frueherer_amtsinhaber_veraltete_fassung(orgs, board_a, api):
    org = orgs["a"]
    chair = Role.objects.create(organization=org, name="1. Vorsitzender", in_chronicle=True)
    c = api(board_a)
    root = f"/api/orgs/{org.pk}/offices/"
    daten = {"role": chair.pk, "name": "Wilhelm Vorzeit", "from_year": 1955, "until_year": 1972}
    made = c.post(root, daten, content_type=JSON)
    assert made.status_code == 201, made.content
    entry = made.json()
    one = f"{root}{entry['id']}/"
    alt = entry["version"]

    resp = c.put(one, {**daten, "from_year": 1956, "version": alt}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    assert resp.json()["version"] > alt

    _stale(c.put(one, {**daten, "from_year": 1957, "version": alt}, content_type=JSON))
    _stale(c.delete(one, {"version": alt}, content_type=JSON))
    assert RoleAssignment.all_objects.get(pk=entry["id"]).valid_from.year == 1956
