"""Minderjährige: Foto-Einwilligung unter 16, Volljährigkeitshinweis (Gesamtaudit 15.11.).

PF-21: Ein Kind setzte über den Upload-Link selbst die Foto-Einwilligung. PF-27: Der Hinweis an
die Erziehungsberechtigten kam nur am genauen Tag (fiel der Lauf aus oder lag der Geburtstag auf
dem 29.02., nie) und bei nur bekanntem Jahrgang endete der Elternzugang bis zu ein Jahr zu früh.
Erfundene Daten.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

import datetime

import pytest
from dateutil.relativedelta import relativedelta
from django.core import mail
from django.core.cache import cache

from core.tenancy import rls_bypass, tenant_context
from members import guardians
from members.models import ContactPerson, Membership, Person, today

from .factories import make_member
from .test_m12_events import cal, private_root  # noqa: F401  (Fixtures)
from .test_photos import _private, image_file, member, types, url  # noqa: F401

pytestmark = pytest.mark.django_db
JSON = "application/json"


def _birth(member_id, birth, year_only=False):
    with rls_bypass():
        person = Person.objects.get(memberships__pk=member_id)
        person.birth_date = birth
        person.birth_year_only = year_only
        person.save(update_fields=["birth_date", "birth_year_only"])


def _upload(client, api, orgs, member, board_a):
    cache.clear()
    resp = api(board_a).post(
        url(orgs, member).replace("photo/", "photo-links/"), {}, content_type=JSON
    )
    assert resp.status_code == 201, resp.json()
    public = "/api/public/photo/" + resp.json()["url"].rsplit("/", 1)[1] + "/"
    return client.post(public, {"file": image_file(), "consent": "true"})


def test_kind_unter_16_willigt_nicht_selbst_ein(client, api, orgs, member, board_a):
    _birth(member["id"], today() - relativedelta(years=12))
    resp = _upload(client, api, orgs, member, board_a)
    assert resp.status_code == 201, resp.json()
    assert resp.json()["status"] == "pending"  # wartet auf den Vorstand
    with rls_bypass():
        m = Membership.objects.get(pk=member["id"])
    assert m.photo_consent_at is None and m.photo_consent_source == ""


def test_ab_16_wie_bisher(client, api, orgs, member, board_a):
    _birth(member["id"], today() - relativedelta(years=16, days=1))
    resp = _upload(client, api, orgs, member, board_a)
    assert resp.status_code == 201
    with rls_bypass():
        m = Membership.objects.get(pk=member["id"])
    assert m.photo_consent_at is not None and m.photo_consent_source == "member"


def _guardian(club, membership):
    with tenant_context(club.pk):
        return ContactPerson.objects.create(
            organization=club,
            membership=membership,
            last_name="Muster",
            first_name="Erika",
            email="erika.eltern@example.org",
            is_guardian=True,
            is_primary=True,
        )


def test_hinweis_auch_nach_ausgefallenem_lauf_und_nur_einmal(cal):
    club = cal["a"]
    # In zehn Tagen volljährig: Der Lauf vor 18 Tagen fiel aus, heute kommt der Hinweis
    birth = today() + datetime.timedelta(days=10) - relativedelta(years=18)
    member = make_member(club, "Tim", "Muster", birth_date=birth)
    _guardian(club, member)
    mail.outbox.clear()
    assert guardians.send_notices() == 1
    assert guardians.send_notices() == 0  # nicht doppelt
    assert len(mail.outbox) == 1
    with rls_bypass():
        assert ContactPerson.objects.get(membership=member).adult_notice_at is not None


def test_nur_jahrgang_endet_erst_am_jahresende(cal):
    club = cal["a"]
    year = today().year - 18
    member = make_member(club, "Ina", "Jahrgang", birth_date=datetime.date(year, 1, 1))
    _birth(member.pk, datetime.date(year, 1, 1), year_only=True)
    _guardian(club, member)
    # Frühestens am 1.1. volljährig, spätestens am 31.12.: Zugang bleibt bis dahin
    with rls_bypass():
        person = Person.objects.get(memberships__pk=member.pk)
    assert guardians.adult_on(person) == datetime.date(today().year, 12, 31)
    if today() < datetime.date(today().year, 12, 31):
        assert guardians.end_adults() == 0
    assert guardians.end_adults(datetime.date(today().year, 12, 31)) == 1
