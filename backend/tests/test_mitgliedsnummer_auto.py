"""Mitgliedsnummer: ohne Eingabe vergibt HUBIplan die nächste freie Nummer des Vereins."""

import pytest

from members.models import Membership
from members.services import next_club_number

from .factories import make_member
from .test_import_organisationen import ADDRESS, HEADER, run_import
from .test_m2_members import admit, make_types

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _eager(settings, tmp_path):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.PRIVATE_ROOT = tmp_path / "private"


@pytest.fixture
def types(orgs):
    return make_types(orgs["a"])


def test_ohne_nummer_wird_fortlaufend_vergeben(api, orgs, types, board_a):
    c = api(board_a)
    first = admit(c, orgs["a"], types["aktiv"])
    assert first.status_code == 201, first.json()
    assert first.json()["club_number"] == "1"
    second = admit(c, orgs["a"], types["aktiv"], last_name="Zweite", birth_date="1990-01-01")
    assert second.json()["club_number"] == "2"


def test_von_hand_vergebene_nummer_bleibt(api, orgs, types, board_a):
    c = api(board_a)
    resp = admit(c, orgs["a"], types["aktiv"], club_number=" A-17 ")
    assert resp.json()["club_number"] == "A-17"
    # Nummern mit Buchstaben zählen nicht mit
    resp = admit(c, orgs["a"], types["aktiv"], last_name="Zweite", birth_date="1990-01-01")
    assert resp.json()["club_number"] == "1"


def test_hoechste_zahl_plus_eins_mit_fuehrenden_nullen(api, orgs, types, board_a):
    c = api(board_a)
    admit(c, orgs["a"], types["aktiv"], club_number="0099")
    admit(
        c, orgs["a"], types["aktiv"], last_name="Zweite", birth_date="1990-01-01", club_number="7"
    )
    resp = admit(c, orgs["a"], types["aktiv"], last_name="Dritte", birth_date="1991-01-01")
    assert resp.json()["club_number"] == "0100"


def test_jeder_verein_zaehlt_fuer_sich(api, orgs, board_a, board_b):
    types_a, types_b = make_types(orgs["a"]), make_types(orgs["b"])
    admit(api(board_a), orgs["a"], types_a["aktiv"], club_number="500")
    resp = admit(api(board_b), orgs["b"], types_b["passiv"], last_name="Beispiel")
    assert resp.json()["club_number"] == "1"


@pytest.mark.parametrize(
    "vorhanden, datei, erwartet",
    [
        ([], [], "1"),
        (["3", "12", "x9"], [], "13"),
        (["3"], ["40", "", "B"], "41"),
        (["007", "8"], [], "009"),
    ],
)
def test_next_club_number(orgs, types, vorhanden, datei, erwartet):
    from core.tenancy import tenant_context

    for i, number in enumerate(vorhanden):
        m = make_member(orgs["a"], "Erika", f"Muster{i}", member_type=types["passiv"])
        m.club_number = number
        m.save(update_fields=["club_number"])
    with tenant_context(orgs["a"].pk):
        assert next_club_number(orgs["a"], datei) == erwartet


def test_import_vergibt_fehlende_nummern(api, orgs, types, board_a):
    c = api(board_a)
    org = orgs["a"]
    admit(c, org, types["aktiv"], club_number="10")

    def row(first, birth, number):
        return ["Person", "Muster", "", "", first, birth, *ADDRESS, number, "", "", "", ""]

    data = [
        HEADER,
        row("Anna", "01.01.1990", ""),
        row("Bernd", "02.01.1990", "20"),
        row("Clara", "03.01.1990", ""),
    ]
    job, checked = run_import(c, org, types, data)
    assert checked["counts"]["errors"] == 0, checked["preview"]
    done = c.post(f"/api/orgs/{org.pk}/imports/{job['id']}/run/").json()
    assert done["status"] == "imported", done
    by_name = {
        m.person.first_name: m.club_number
        for m in Membership.objects.filter(organization=org).select_related("person")
    }
    assert by_name == {"Erika": "10", "Anna": "21", "Bernd": "20", "Clara": "22"}
