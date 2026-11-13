"""Erziehungsberechtigte und Elternzugang (Konzept Familien, Haushalte und Firmen, H4)."""
# ruff: noqa: F811  (Fixtures aus test_m12_events als Parameter)

import datetime

import pytest
from dateutil.relativedelta import relativedelta
from django.core import mail

from core.tenancy import tenant_context
from members import guardians
from members.models import ContactPerson, today
from portal.models import PortalAccess

from .factories import make_member
from .test_m12_events import JSON, board_fed, cal, private_root  # noqa: F401  (Fixtures)
from .test_rundschreiben import base, draft, preview

pytestmark = pytest.mark.django_db


def contacts_url(club, member):
    return f"/api/orgs/{club.pk}/members/{member.pk}/contacts/"


@pytest.fixture
def kind(cal):
    return make_member(
        cal["a"],
        "Lisa",
        "Muster",
        email="lisa@example.org",
        birth_date=today() - relativedelta(years=12),
    )


def add_guardian(c, club, member, **data):
    payload = {"last_name": "Muster", "first_name": "Erika", "email": "erika@example.org", **data}
    return c.post(contacts_url(club, member), payload, content_type=JSON)


class TestEintragen:
    def test_bei_minderjaehrigen(self, api, cal, board_a, kind):
        resp = add_guardian(api(board_a), cal["a"], kind)
        assert resp.status_code == 201, resp.json()
        assert resp.json()["is_guardian"] is True
        assert ContactPerson.objects.get().is_guardian

    def test_nicht_bei_erwachsenen(self, api, cal, board_a):
        adult = make_member(cal["a"], "Max", "Muster")
        resp = add_guardian(api(board_a), cal["a"], adult)
        assert resp.status_code == 400
        assert not ContactPerson.objects.exists()

    def test_elternzugang(self, api, cal, board_a, kind):
        club = cal["a"]
        club.member_portal_enabled = True
        club.save()
        c = api(board_a)
        contact = add_guardian(c, club, kind).json()
        resp = c.post(
            f"/api/orgs/{club.pk}/members/{kind.pk}/access/?ansprechpartner={contact['id']}"
        )
        assert resp.status_code in (200, 201), resp.json()
        access = PortalAccess.objects.get(contact_person_id=contact["id"])
        assert access.user.email == "erika@example.org"


class TestVolljaehrig:
    def _guardian(self, club, member, with_access=False):
        with tenant_context(club.pk):
            contact = ContactPerson.objects.create(
                organization=club,
                membership=member,
                last_name="Muster",
                first_name="Erika",
                email="erika@example.org",
                is_guardian=True,
                is_primary=True,
            )
        return contact

    def test_endet_am_18_geburtstag(self, api, cal, board_a):
        club = cal["a"]
        club.member_portal_enabled = True
        club.save()
        member = make_member(club, "Tim", "Muster", birth_date=today() - relativedelta(years=18))
        contact = self._guardian(club, member)
        c = api(board_a)
        c.post(f"/api/orgs/{club.pk}/members/{member.pk}/access/?ansprechpartner={contact.pk}")
        assert PortalAccess.objects.filter(contact_person=contact).exists()
        # noch minderjährig: bleibt
        young = make_member(club, "Ina", "Muster", birth_date=today() - relativedelta(years=17))
        self._guardian(club, young)
        assert guardians.end_adults() == 1
        assert not PortalAccess.objects.filter(contact_person_id=contact.pk).exists()
        assert list(ContactPerson.objects.values_list("membership_id", flat=True)) == [young.pk]

    def test_hinweis_vier_wochen_vorher(self, cal):
        club = cal["a"]
        birth = today() + datetime.timedelta(days=guardians.NOTICE_DAYS) - relativedelta(years=18)
        member = make_member(club, "Tim", "Muster", birth_date=birth)
        self._guardian(club, member)
        mail.outbox.clear()
        assert guardians.send_notices() == 1
        assert mail.outbox[0].to == ["erika@example.org"]
        assert "Tim Muster" in mail.outbox[0].body


class TestRundschreiben:
    def test_mail_auch_an_erziehungsberechtigte(self, api, cal, board_a, kind):
        c = api(board_a)
        club = cal["a"]
        add_guardian(c, club, kind)
        add_guardian(c, club, kind, first_name="Max", email="lisa@example.org")
        url = base(club)
        data = draft(c, url)
        rows = [i for i in preview(c, url, data["id"])["items"] if i["last_name"] == "Muster"]
        # Lisa selbst und Erika; Max hat dieselbe Adresse wie Lisa
        assert sorted(r["first_name"] for r in rows) == ["Erika", "Lisa"]
