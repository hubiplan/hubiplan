"""Firmen zahlen für Mitarbeiter (Konzept Familien, Haushalte und Firmen, H5). Alles erfunden."""
# ruff: noqa: F811  (Fixtures aus test_mitgliedsantrag als Parameter)

import datetime
from urllib.parse import unquote

import pytest
from django.core import mail, signing
from django.test import Client

from billing import company_portal
from billing.company_portal import SALT, invite_token
from core.tenancy import tenant_context
from members.models import Household, HouseholdMember, Membership, today
from portal.models import PortalAccess

from .factories import make_member
from .test_mitgliedsantrag import (  # noqa: F401  (Fixtures, auch die automatische)
    app_of,
    club,
    leichte_aufgabe,
    schema,
    submit,
    token_from_mail,
)
from .test_organisationsmitglieder import admit_org

pytestmark = pytest.mark.django_db(transaction=True)
JSON = "application/json"


@pytest.fixture
def firma(club, api):
    org = club["org"]
    org.member_portal_enabled = True
    org.contact_email = "vorstand@example.org"
    org.save()
    c = club["client"]
    res = admit_org(c, org, club["aktiv"])
    assert res.status_code == 201, res.content
    org_member = res.json()["id"]
    members = f"/api/orgs/{org.pk}/members/{org_member}/"
    contact = c.post(
        f"{members}contacts/",
        {"last_name": "Beispiel", "first_name": "Petra", "email": "petra@musterbau.example"},
        content_type=JSON,
    ).json()
    res = c.post(f"{members}access/?ansprechpartner={contact['id']}")
    assert res.status_code in (200, 201), res.content
    hh = c.post(
        f"/api/orgs/{org.pk}/households/",
        {"name": "Musterbau GmbH", "kind": "company"},
        content_type=JSON,
    ).json()
    res = c.put(
        f"/api/orgs/{org.pk}/billing/households/{hh['id']}/payer/",
        {"kind": "organization", "membership": org_member},
        content_type=JSON,
    )
    assert res.status_code == 200, res.content
    ina = make_member(org, "Ina", "Beispiel", "ina@example.org")
    res = c.post(
        f"/api/orgs/{org.pk}/households/{hh['id']}/members/",
        {"membership": ina.pk, "valid_from": "2025-01-01", "pays_via": True},
        content_type=JSON,
    )
    assert res.status_code == 201, res.content
    access = PortalAccess.objects.get(contact_person_id=contact["id"])
    return {
        **club,
        "household": hh["id"],
        "ina": ina,
        "access": access,
        "portal": api(access.user),
        "url": f"/api/portal/{access.pk}/company/",
    }


class TestListe:
    def test_nur_name_seit_und_beitrag(self, firma):
        data = firma["portal"].get(firma["url"]).json()
        assert data["can_report"] is True
        [company] = data["companies"]
        assert company["name"] == "Musterbau GmbH"
        [row] = company["members"]
        assert row["name"] == "Ina Beispiel"
        assert row["since"] == "2025-01-01"
        assert row["pays_via"] is True
        assert set(row) == {"link", "name", "since", "until", "pays_via"}

    def test_menuepunkt(self, firma):
        portal = firma["portal"].get("/api/me/contexts/").json()["portal"]
        assert [p["company"] for p in portal] == [True]

    def test_eigener_zugang_sieht_keine_firma(self, firma, api):
        org = firma["org"]
        firma["client"].post(f"/api/orgs/{org.pk}/members/{firma['ina'].pk}/access/")
        access = PortalAccess.objects.get(membership=firma["ina"], contact_person=None)
        assert api(access.user).get(f"/api/portal/{access.pk}/company/").status_code == 404


class TestMelden:
    def test_melden_antrag_und_annahme(self, firma):
        mail.outbox.clear()
        res = firma["portal"].post(
            f"{firma['url']}{firma['household']}/report/",
            {"first_name": "Tom", "last_name": "Muster", "email": "tom@example.org"},
            content_type=JSON,
        )
        assert res.status_code == 201, res.content
        [invite] = mail.outbox
        assert invite.to == ["tom@example.org"]
        assert "Musterbau GmbH" in invite.body
        link = next(w for w in invite.body.split() if "/mitglied-werden/" in w)
        # Name und Mailadresse stehen nicht lesbar im Link (Gesamtaudit 13.11. S-01)
        assert "firma=" in link
        assert "Tom" not in link and "Muster" not in link and "example.org" not in link
        token = unquote(link.split("firma=")[1])
        data = schema(firma["key"], firma=token)
        assert data["company"] == "Musterbau GmbH"
        assert data["invite"] == {
            "email": "tom@example.org",
            "first_name": "Tom",
            "last_name": "Muster",
        }
        assert schema(firma["key"])["company"] is None
        assert schema(firma["key"])["invite"] is None

        mail.outbox.clear()
        res = submit(
            firma["key"],
            first_name="Tom",
            email="tom@example.org",
            company=token,
            confirmations=["privacy"],
        )
        assert res.status_code == 201, res.content
        confirm = token_from_mail(mail.outbox[-1])
        Client().post(f"/api/public/join/application/{confirm}/confirm/")
        app = app_of(firma["org"])
        base = f"/api/orgs/{firma['org'].pk}/admission/"
        res = firma["client"].post(f"{base}{app.pk}/accept/", {"invite": False}, JSON)
        assert res.status_code == 200, res.content
        app.refresh_from_db()
        with tenant_context(firma["org"].pk):
            membership = Membership.objects.get(pk=app.membership_id)
            link = HouseholdMember.objects.get(membership=membership)
            assert link.household_id == firma["household"]
            assert link.pays_via is True

    def test_ungueltiger_link(self, firma):
        res = submit(firma["key"], company="kaputt", confirmations=["privacy"])
        assert res.status_code == 400
        assert "company" in res.json()

    def test_link_gilt_nur_fuer_die_gemeldete_adresse(self, firma):
        """Gesamtaudit 13.11. S-04: Weitergereicht nützt der Link niemandem."""
        with tenant_context(firma["org"].pk):
            token = invite_token(
                Household.objects.get(pk=firma["household"]), "tom@example.org", "Tom", "Muster"
            )
        res = submit(
            firma["key"], email="fremd@example.org", company=token, confirmations=["privacy"]
        )
        assert res.status_code == 400 and "email" in res.json()
        res = submit(
            firma["key"], email="Tom@Example.org", company=token, confirmations=["privacy"]
        )
        assert res.status_code == 201, res.content

    def test_alter_link_gilt_weiter(self, firma):
        """Links aus der Zeit vor der Verschlüsselung bleiben bis zum Ablauf gültig."""
        old = signing.dumps(
            {"o": firma["org"].pk, "h": firma["household"], "e": "tom@example.org"}, salt=SALT
        )
        data = schema(firma["key"], firma=old)
        assert data["company"] == "Musterbau GmbH"
        assert data["invite"]["email"] == "tom@example.org"

    def test_grenzen(self, firma, monkeypatch):
        """Gesamtaudit 13.11. S-01: keine Mailflut im Namen des Vereins."""
        url = f"{firma['url']}{firma['household']}/report/"

        def melden(mail_address, first="Tom", last="Muster"):
            return firma["portal"].post(
                url,
                {"first_name": first, "last_name": last, "email": mail_address},
                content_type=JSON,
            )

        mail.outbox.clear()
        assert melden("tom@example.org").status_code == 201
        # dieselbe Adresse nur einmal am Tag, auch anders geschrieben
        res = melden("Tom@Example.org")
        assert res.status_code == 400 and "email" in res.json()
        # im Namen steht nur, was in Namen vorkommt
        for name in ("https://example.org", "Jetzt gewinnen!", "www.example.org", "A1"):
            res = melden("anna@example.org", first=name)
            assert res.status_code == 400 and "first_name" in res.json(), name
        assert melden("anna@example.org", first="Anna-Lena", last="O’Neil").status_code == 201
        assert len(mail.outbox) == 2
        # Grenze je Firma
        monkeypatch.setattr(company_portal, "REPORTS_PER_COMPANY", 3)
        assert melden("b@example.org").status_code == 201
        res = melden("c@example.org")
        assert res.status_code == 400 and "detail" in res.json()
        assert len(mail.outbox) == 3

    def test_ohne_online_antrag(self, firma):
        org = firma["org"]
        firma["client"].patch(f"/api/orgs/{org.pk}/admission/form/", {"enabled": False}, JSON)
        res = firma["portal"].post(
            f"{firma['url']}{firma['household']}/report/",
            {"first_name": "Tom", "last_name": "Muster", "email": "tom@example.org"},
            content_type=JSON,
        )
        assert res.status_code == 400


class TestAbmelden:
    def test_firma_zahlt_nicht_mehr(self, firma):
        link = firma["portal"].get(firma["url"]).json()["companies"][0]["members"][0]["link"]
        url = f"{firma['url']}{firma['household']}/members/{link}/end/"
        past = (today() - datetime.timedelta(days=1)).isoformat()
        assert (
            firma["portal"].post(url, {"valid_until": past}, content_type=JSON).status_code == 400
        )
        mail.outbox.clear()
        res = firma["portal"].post(url, {"valid_until": today().isoformat()}, content_type=JSON)
        assert res.status_code == 200, res.content
        assert res.json()["members"][0]["until"] == today().isoformat()
        assert sorted(m.to[0] for m in mail.outbox) == ["ina@example.org", "vorstand@example.org"]
        with tenant_context(firma["org"].pk):
            # kein Austritt: die Mitgliedschaft bleibt
            assert Membership.objects.get(pk=firma["ina"].pk).current_period() is not None


IBAN = "DE89370400440532013000"


@pytest.fixture
def familienformular(club):
    org = club["org"]
    res = club["client"].patch(
        f"/api/orgs/{org.pk}/admission/form/",
        {"fields": {"birth_date": "optional", "phone": "optional", "family": "optional"}},
        JSON,
    )
    assert res.status_code == 200, res.content
    assert schema(club["key"])["fields"]["family"] == "optional"
    return club


class TestFamilienantrag:
    """Familienantrag (H6): mehrere Personen, gemeinsame Anschrift, ein Mandat."""

    def test_annahme_legt_haushalt_an(self, familienformular):
        club = familienformular
        org = club["org"]
        mail.outbox.clear()
        res = submit(
            club["key"],
            mandate={"holder": "Max Muster", "iban": IBAN},
            family=[
                {"first_name": "Lisa", "birth_date": "2014-03-01"},
                {"first_name": "Erika", "last_name": "Beispiel", "birth_date": "1985-01-01"},
            ],
        )
        assert res.status_code == 201, res.content
        confirm = token_from_mail(mail.outbox[-1])
        Client().post(f"/api/public/join/application/{confirm}/confirm/")
        app = app_of(org)
        base = f"/api/orgs/{org.pk}/admission/"
        detail = club["client"].get(f"{base}{app.pk}/").json()
        assert "Lisa Muster" in str(detail)
        res = club["client"].post(f"{base}{app.pk}/accept/", {"invite": False}, JSON)
        assert res.status_code == 200, res.content
        app.refresh_from_db()
        with tenant_context(org.pk):
            from billing.models import HouseholdPayer
            from members.models import ContactPerson

            household = Household.objects.get(kind="family")
            assert household.name == "Familie Muster"
            links = {
                link.membership.person.first_name: link
                for link in household.members.select_related("membership__person")
            }
            assert set(links) == {"Max", "Lisa", "Erika"}
            assert links["Lisa"].role == "child" and links["Erika"].role == "adult"
            assert all(link.pays_via for link in links.values())
            assert links["Erika"].membership.person.last_name == "Beispiel"
            payer = HouseholdPayer.objects.get(household=household)
            assert payer.membership_id == app.membership_id
            guardian = ContactPerson.objects.get(membership=links["Lisa"].membership)
            assert guardian.is_guardian and guardian.person_id == links["Max"].membership.person_id

    def test_ohne_einstellung_keine_weiteren_personen(self, club):
        mail.outbox.clear()
        res = submit(
            club["key"],
            mandate={"holder": "Max Muster", "iban": IBAN},
            family=[{"first_name": "Lisa"}],
        )
        assert res.status_code == 201, res.content
        assert "family" not in app_of(club["org"]).data

    def test_vorname_pflicht(self, familienformular):
        res = submit(
            familienformular["key"],
            mandate={"holder": "Max Muster", "iban": IBAN},
            family=[{"first_name": ""}],
        )
        assert res.status_code == 400
        assert "family" in res.json()
