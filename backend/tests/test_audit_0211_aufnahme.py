"""Audit 02.11. GA-S01: eine vorhandene Person nur über einen echten Dublettenfund verknüpfen.

Die Personen-ID allein berechtigt nicht; Name und Geburtsdatum müssen zur Person passen.
Bei der direkten Aufnahme bleibt die gemeinsame Anschrift des anderen Vereins unverändert.
"""

import pytest

from members.models import ContactDetails, Membership, TransferRequest

from .factories import found
from .test_m2_members import JSON, admit, make_types

pytestmark = pytest.mark.django_db


@pytest.fixture
def types(orgs):
    return {key: make_types(orgs[key]) for key in ("a", "b")}


@pytest.fixture
def erika(api, orgs, types, board_a):
    resp = admit(api(board_a), orgs["a"], types["a"]["aktiv"])
    assert resp.status_code == 201, resp.json()
    return resp.json()


def link(client, org, member_type, person_id, **extra):
    data = {
        "person": person_id,
        "member_type": member_type.pk,
        "entry_date": "2021-01-01",
        "email": "fremd@example.org",
        "street": "Fremdweg 9",
        "postal_code": "99999",
        "city": "Anderswo",
    }
    data.update(extra)
    return client.post(f"/api/orgs/{org.pk}/members/admit/", data, content_type=JSON)


def contact_of(person_id):
    contact = ContactDetails.objects.get(person_id=person_id, organization=None)
    return {f: getattr(contact, f) for f in ("email", "street", "postal_code", "city")}


class TestVerknuepfen:
    def test_nur_personen_id_wird_abgewiesen(self, api, orgs, types, erika, board_b):
        before = contact_of(erika["person_id"])
        resp = link(api(board_b), orgs["b"], types["b"]["passiv"], erika["person_id"])
        assert resp.status_code == 400
        body = str(resp.json())
        assert "Muster" not in body and "erika@example.org" not in body
        assert not Membership.objects.filter(organization=orgs["b"]).exists()
        assert contact_of(erika["person_id"]) == before

    def test_falsches_geburtsdatum_wird_abgewiesen(self, api, orgs, types, erika, board_b):
        resp = link(
            api(board_b),
            orgs["b"],
            types["b"]["passiv"],
            erika["person_id"],
            last_name="Muster",
            first_name="Erika",
            birth_date="1981-05-17",
        )
        assert resp.status_code == 400
        assert "person" in resp.json()
        assert not Membership.objects.filter(organization=orgs["b"]).exists()

    def test_fremder_name_wird_abgewiesen(self, api, orgs, types, erika, board_b):
        resp = link(
            api(board_b),
            orgs["b"],
            types["b"]["passiv"],
            erika["person_id"],
            last_name="Anders",
            first_name="Otto",
            birth_date="1980-05-17",
        )
        assert resp.status_code == 400
        assert not Membership.objects.filter(organization=orgs["b"]).exists()

    def test_mit_passenden_angaben_erlaubt(self, api, orgs, types, erika, board_b):
        resp = link(
            api(board_b),
            orgs["b"],
            types["b"]["passiv"],
            erika["person_id"],
            last_name="muster",
            first_name="Erika",
            birth_date="1980-05-17",
        )
        assert resp.status_code == 201, resp.json()
        assert resp.json()["person_id"] == erika["person_id"]

    def test_gemeinsame_anschrift_bleibt(self, api, orgs, types, erika, board_b):
        before = contact_of(erika["person_id"])
        resp = link(
            api(board_b),
            orgs["b"],
            types["b"]["passiv"],
            erika["person_id"],
            **found(erika["person_id"]),
        )
        assert resp.status_code == 201, resp.json()
        assert contact_of(erika["person_id"]) == before

    def test_leere_angaben_werden_ergaenzt(self, api, orgs, types, erika, board_b):
        ContactDetails.objects.filter(person_id=erika["person_id"]).update(email="")
        resp = link(
            api(board_b),
            orgs["b"],
            types["b"]["passiv"],
            erika["person_id"],
            **found(erika["person_id"]),
        )
        assert resp.status_code == 201, resp.json()
        after = contact_of(erika["person_id"])
        assert after["email"] == "fremd@example.org"
        assert after["street"] != "Fremdweg 9"


class TestWechselanfrage:
    def test_nur_personen_id_wird_abgewiesen(self, api, orgs, types, erika, board_b):
        resp = api(board_b).post(
            f"/api/orgs/{orgs['b'].pk}/transfers/",
            {
                "person": erika["person_id"],
                "member_type": types["b"]["aktiv"].pk,
                "entry_date": "2024-07-01",
                "street": "Neuweg 1",
                "postal_code": "54321",
                "city": "Neustadt",
            },
            content_type=JSON,
        )
        assert resp.status_code == 400
        assert not TransferRequest.objects.exists()

    def test_falsche_angaben_werden_abgewiesen(self, api, orgs, types, erika, board_b):
        resp = api(board_b).post(
            f"/api/orgs/{orgs['b'].pk}/transfers/",
            {
                "person": erika["person_id"],
                "last_name": "Muster",
                "first_name": "Erika",
                "birth_date": "1990-01-01",
                "member_type": types["b"]["aktiv"].pk,
                "entry_date": "2024-07-01",
                "street": "Neuweg 1",
                "postal_code": "54321",
                "city": "Neustadt",
            },
            content_type=JSON,
        )
        assert resp.status_code == 400
        assert not TransferRequest.objects.exists()
