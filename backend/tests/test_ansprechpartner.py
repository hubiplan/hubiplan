"""Ansprechpartner von Organisationsmitgliedern (Konzept juristische Personen, J2)."""

import io
import json
import zipfile

import pytest

from members.models import ContactPerson, Membership
from members.workflows import _purge_membership

from .test_m2_members import admit, make_types
from .test_organisationsmitglieder import admit_org

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture
def types(orgs):
    return {key: make_types(orgs[key]) for key in ("a", "b")}


@pytest.fixture
def firma(api, orgs, types, board_a):
    resp = admit_org(api(board_a), orgs["a"], types["a"]["foerder"])
    assert resp.status_code == 201, resp.json()
    return resp.json()


def url(org, member_id, pk=None):
    base = f"/api/orgs/{org.pk}/members/{member_id}/contacts/"
    return f"{base}{pk}/" if pk else base


class TestAnlegen:
    def test_frei_erfasst_wird_hauptansprechpartner(self, api, orgs, firma, board_a):
        c = api(board_a)
        resp = c.post(
            url(orgs["a"], firma["id"]),
            {
                "last_name": "Muster",
                "first_name": "Max",
                "function": "Geschäftsführer",
                "email": "max@musterbau.example",
                "phone": "0123 4567",
            },
            content_type=JSON,
        )
        assert resp.status_code == 201, resp.json()
        data = resp.json()
        assert data["is_primary"] is True
        assert data["display_name"] == "Max Muster"
        assert data["contact_email"] == "max@musterbau.example"
        assert (data["receives_mail"], data["receives_invoices"], data["represents"]) == (
            True,
            True,
            True,
        )
        assert data["member_access"] is False
        akte = c.get(f"/api/orgs/{orgs['a'].pk}/members/{firma['id']}/").json()
        assert [p["display_name"] for p in akte["contact_persons"]] == ["Max Muster"]

    def test_name_pflicht(self, api, orgs, firma, board_a):
        resp = api(board_a).post(url(orgs["a"], firma["id"]), {"function": "x"}, content_type=JSON)
        assert resp.status_code == 400
        assert not ContactPerson.objects.exists()

    def test_nur_bei_organisationen(self, api, orgs, types, board_a):
        c = api(board_a)
        person = admit(c, orgs["a"], types["a"]["aktiv"]).json()
        resp = c.post(url(orgs["a"], person["id"]), {"last_name": "Muster"}, content_type=JSON)
        assert resp.status_code == 400
        assert (
            api(board_a)
            .get(f"/api/orgs/{orgs['a'].pk}/members/{person['id']}/")
            .json()["contact_persons"]
            == []
        )

    def test_anderer_verein_sieht_nichts(self, api, orgs, firma, board_a, board_b):
        c = api(board_a)
        made = c.post(url(orgs["a"], firma["id"]), {"last_name": "Muster"}, content_type=JSON)
        assert made.status_code == 201
        resp = api(board_b).get(url(orgs["a"], firma["id"]))
        assert resp.status_code in (403, 404)


class TestVerknuepft:
    def test_mitglied_als_ansprechpartner(self, api, orgs, types, firma, board_a):
        c = api(board_a)
        person = admit(c, orgs["a"], types["a"]["aktiv"]).json()
        resp = c.post(
            url(orgs["a"], firma["id"]),
            {"member": person["id"], "last_name": "wird verworfen", "function": "Prokurist"},
            content_type=JSON,
        )
        assert resp.status_code == 201, resp.json()
        data = resp.json()
        assert data["linked_member"] == person["id"]
        assert data["last_name"] == ""
        assert data["display_name"] == f"{person['first_name']} {person['last_name']}"
        assert data["contact_email"] == "erika@example.org"
        # Zweimal dieselbe Person geht nicht
        again = c.post(url(orgs["a"], firma["id"]), {"member": person["id"]}, content_type=JSON)
        assert again.status_code == 400
        # Die Akte der Person zeigt, wofür sie Ansprechpartner ist
        akte = c.get(f"/api/orgs/{orgs['a'].pk}/members/{person['id']}/").json()
        assert akte["contact_for"] == [
            {"member_id": firma["id"], "name": "Musterbau GmbH – Niederlassung Musterstadt"}
        ]

    def test_organisation_ist_kein_ansprechpartner(self, api, orgs, types, firma, board_a):
        c = api(board_a)
        other = admit_org(c, orgs["a"], types["a"]["foerder"], last_name="Zweite AG").json()
        resp = c.post(url(orgs["a"], firma["id"]), {"member": other["id"]}, content_type=JSON)
        assert resp.status_code == 400


class TestHauptansprechpartner:
    def test_genau_einer(self, api, orgs, firma, board_a):
        c = api(board_a)
        first = c.post(url(orgs["a"], firma["id"]), {"last_name": "Eins"}, content_type=JSON)
        second = c.post(
            url(orgs["a"], firma["id"]),
            {"last_name": "Zwei", "is_primary": True},
            content_type=JSON,
        )
        assert second.status_code == 201, second.json()
        primary = ContactPerson.objects.filter(is_primary=True)
        assert [p.last_name for p in primary] == ["Zwei"]
        # Hauptansprechpartner entfernen: der nächste rückt nach
        assert c.delete(url(orgs["a"], firma["id"], second.json()["id"])).status_code == 204
        assert ContactPerson.objects.get().pk == first.json()["id"]
        assert ContactPerson.objects.get().is_primary

    def test_abwaehlen_nicht_moeglich_wenn_einziger(self, api, orgs, firma, board_a):
        c = api(board_a)
        made = c.post(url(orgs["a"], firma["id"]), {"last_name": "Eins"}, content_type=JSON)
        resp = c.patch(
            url(orgs["a"], firma["id"], made.json()["id"]),
            {"is_primary": False, "receives_invoices": False},
            content_type=JSON,
        )
        assert resp.status_code == 200, resp.json()
        cp = ContactPerson.objects.get()
        assert cp.is_primary and not cp.receives_invoices


class TestDatenschutz:
    def test_entfernen_loescht_kontaktdaten(self, api, orgs, firma, board_a):
        c = api(board_a)
        made = c.post(
            url(orgs["a"], firma["id"]),
            {"last_name": "Muster", "email": "max@musterbau.example"},
            content_type=JSON,
        )
        assert c.delete(url(orgs["a"], firma["id"], made.json()["id"])).status_code == 204
        assert not ContactPerson.objects.exists()

    def test_loeschfrist_entfernt_ansprechpartner(self, api, orgs, types, firma, board_a):
        c = api(board_a)
        person = admit(c, orgs["a"], types["a"]["aktiv"]).json()
        c.post(url(orgs["a"], firma["id"]), {"last_name": "Muster"}, content_type=JSON)
        c.post(url(orgs["a"], firma["id"]), {"member": person["id"]}, content_type=JSON)
        assert ContactPerson.objects.count() == 2
        _purge_membership(Membership.objects.get(pk=person["id"]))
        assert ContactPerson.objects.count() == 1
        _purge_membership(Membership.objects.get(pk=firma["id"]))
        assert not ContactPerson.objects.exists()

    def test_auskunft_enthaelt_ansprechpartner(self, api, orgs, firma, board_a):
        from members import auskunft

        c = api(board_a)
        c.post(url(orgs["a"], firma["id"]), {"last_name": "Muster"}, content_type=JSON)
        data = auskunft.build(Membership.objects.get(pk=firma["id"]), orgs["a"])
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            akte = json.loads(zf.read("akte.json"))
        assert [p["display_name"] for p in akte["contact_persons"]] == ["Muster"]
