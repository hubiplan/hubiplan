"""Mitgliederzugang je Ansprechpartner und Ausweis für Organisationen (Konzept J5)."""

import pytest
from django.core import mail

from cards import services as card_services
from cards.models import MemberCard
from core.tenancy import tenant_context
from members.models import ContactPerson, Membership
from members.workflows import _purge_membership
from portal.models import PortalAccess

from .test_m2_members import admit, make_types
from .test_organisationsmitglieder import admit_org

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture
def club(orgs):
    club = orgs["a"]
    club.member_portal_enabled = True
    club.save()
    return club


@pytest.fixture
def types(club):
    return make_types(club)


@pytest.fixture
def firma(api, club, types, board_a):
    resp = admit_org(api(board_a), club, types["foerder"])
    assert resp.status_code == 201, resp.json()
    return resp.json()


def add_contact(client, club, member_id, **data):
    resp = client.post(
        f"/api/orgs/{club.pk}/members/{member_id}/contacts/", data, content_type=JSON
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()


def access_url(club, member_id, contact_id=None):
    base = f"/api/orgs/{club.pk}/members/{member_id}/access/"
    return f"{base}?ansprechpartner={contact_id}" if contact_id else base


class TestZugangJeAnsprechpartner:
    def test_zwei_ansprechpartner_zwei_zugaenge(self, api, club, firma, board_a):
        c = api(board_a)
        max_ = add_contact(
            c,
            club,
            firma["id"],
            last_name="Muster",
            first_name="Max",
            email="max@musterbau.example",
        )
        eva = add_contact(
            c,
            club,
            firma["id"],
            last_name="Beispiel",
            first_name="Eva",
            email="eva@musterbau.example",
        )
        mail.outbox.clear()
        for contact in (max_, eva):
            resp = c.post(access_url(club, firma["id"], contact["id"]))
            assert resp.status_code == 200, resp.json()
        accesses = PortalAccess.objects.filter(membership_id=firma["id"])
        assert {a.user.email for a in accesses} == {
            "max@musterbau.example",
            "eva@musterbau.example",
        }
        assert len(mail.outbox) == 2
        assert "Ansprechpartner" in mail.outbox[0].body
        assert ContactPerson.objects.filter(member_access=True).count() == 2
        # Status je Ansprechpartner
        info = c.get(access_url(club, firma["id"], max_["id"])).json()
        assert info["access"]["email"] == "max@musterbau.example"
        # Die Akte zeigt die Anmeldeadresse beim Ansprechpartner
        akte = c.get(f"/api/orgs/{club.pk}/members/{firma['id']}/").json()
        emails = {p["display_name"]: p["access_email"] for p in akte["contact_persons"]}
        assert emails["Max Muster"] == "max@musterbau.example"
        # Sperren betrifft nur diesen Ansprechpartner
        assert c.delete(access_url(club, firma["id"], max_["id"])).status_code == 204
        assert [a.user.email for a in PortalAccess.objects.filter(membership_id=firma["id"])] == [
            "eva@musterbau.example"
        ]
        assert not ContactPerson.objects.get(pk=max_["id"]).member_access

    def test_organisation_ohne_ansprechpartner_abgelehnt(self, api, club, firma, board_a):
        resp = api(board_a).post(access_url(club, firma["id"]))
        assert resp.status_code == 400
        assert not PortalAccess.objects.exists()

    def test_ansprechpartner_ohne_adresse(self, api, club, firma, board_a):
        c = api(board_a)
        contact = add_contact(c, club, firma["id"], last_name="Ohne")
        resp = c.post(access_url(club, firma["id"], contact["id"]))
        assert resp.status_code == 400
        assert not PortalAccess.objects.exists()

    def test_fremder_ansprechpartner_nicht_gefunden(self, api, club, types, firma, board_a):
        c = api(board_a)
        other = admit_org(c, club, types["foerder"], last_name="Zweite AG").json()
        contact = add_contact(c, club, other["id"], last_name="X", email="x@zweite.example")
        assert c.post(access_url(club, firma["id"], contact["id"])).status_code == 404

    def test_mitglied_mit_eigenem_und_ansprechpartner_zugang(
        self, api, club, types, firma, board_a
    ):
        c = api(board_a)
        person = admit(c, club, types["aktiv"]).json()
        assert c.post(access_url(club, person["id"])).status_code == 200
        contact = add_contact(c, club, firma["id"], member=person["id"])
        assert c.post(access_url(club, firma["id"], contact["id"])).status_code == 200
        accesses = PortalAccess.objects.all()
        assert len({a.user_id for a in accesses}) == 1
        user = accesses[0].user
        contexts = api(user).get("/api/me/contexts/").json()["portal"]
        kinds = sorted((p["member_kind"], p["member_name"], p["first_name"]) for p in contexts)
        assert kinds == [
            ("organization", "Musterbau GmbH – Niederlassung Musterstadt", "Erika"),
            ("person", "Erika Muster", "Erika"),
        ]

    def test_austritt_entfernt_alle_zugaenge(self, api, club, firma, board_a):
        c = api(board_a)
        for name in ("Eins", "Zwei"):
            contact = add_contact(
                c, club, firma["id"], last_name=name, email=f"{name.lower()}@musterbau.example"
            )
            c.post(access_url(club, firma["id"], contact["id"]))
        assert PortalAccess.objects.count() == 2
        _purge_membership(Membership.objects.get(pk=firma["id"]))
        assert not PortalAccess.objects.exists()


class TestMitgliederbereich:
    def test_ansprechpartner_sieht_daten_der_organisation(self, api, club, firma, board_a):
        c = api(board_a)
        contact = add_contact(
            c,
            club,
            firma["id"],
            last_name="Muster",
            first_name="Max",
            email="max@musterbau.example",
        )
        c.post(access_url(club, firma["id"], contact["id"]))
        access = PortalAccess.objects.get()
        m = api(access.user)
        data = m.get(f"/api/portal/{access.pk}/").json()
        assert data["kind"] == "organization"
        assert data["display_name"] == "Musterbau GmbH – Niederlassung Musterstadt"
        # Vorname, Geburtsdatum und Geschlecht gibt es bei Organisationen nicht
        resp = m.post(
            f"/api/portal/{access.pk}/change-requests/",
            {"first_name": "Unsinn", "phone": "0123 999"},
            content_type=JSON,
        )
        assert resp.status_code in (200, 201), resp.json()
        assert "first_name" not in resp.json()["applied"]
        assert resp.json()["request"] is None


class TestAusweis:
    def test_pruefseite_zeigt_organisation(self, api, club, firma, board_a):
        membership = Membership.objects.get(pk=firma["id"])
        with tenant_context(club.pk):
            card = card_services.ensure_card(membership)
        data = card_services.public_data(card)
        assert data["kind"] == "organization"
        assert data["first_name"] == ""
        assert data["last_name"] == "Musterbau GmbH – Niederlassung Musterstadt"

    def test_ausweis_pdf_ohne_logo(self, api, club, firma, board_a):
        membership = Membership.objects.get(pk=firma["id"])
        with tenant_context(club.pk):
            card = MemberCard.objects.create(organization=club, membership=membership)
            entries = card_services.card_entries([card])
            assert entries[0]["organization"] is True
            assert entries[0]["first_name"] == "Organisationsmitglied"
            assert card_services.render_pdf(entries).startswith(b"%PDF")

    def test_logo_ohne_einwilligung(self, api, club, firma, board_a):
        from io import BytesIO

        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (300, 120), "navy").save(buf, "PNG")
        buf.seek(0)
        buf.name = "logo.png"
        resp = api(board_a).post(f"/api/orgs/{club.pk}/members/{firma['id']}/photo/", {"file": buf})
        assert resp.status_code in (200, 201), resp.json()
        assert Membership.objects.get(pk=firma["id"]).photo_consent_at is not None
