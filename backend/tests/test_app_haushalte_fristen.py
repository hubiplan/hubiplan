"""Android-App: Haushalte in der Akte, Qualifikationen und Fristenkalender nur lesen.

Alles erfunden."""
# ruff: noqa: F811  (Fixtures als Parameter)

import datetime

import pytest

from core.tenancy import tenant_context
from members.models import Household, HouseholdMember, today
from obligations.models import Obligation
from qualifications.models import Qualification, QualificationType

from .factories import give_role, make_member
from .test_app_devices import APP, app
from .test_app_verwaltung import admin_token, board  # noqa: F401
from .test_m12_events import JSON, cal  # noqa: F401

pytestmark = pytest.mark.django_db
ADMIN = f"{APP}admin/u/"


@pytest.fixture
def org(cal):
    org = cal["a"]
    org.enabled_modules = sorted({*org.enabled_modules, "qualifications", "obligations"})
    org.save()
    return org


@pytest.fixture
def base(org):
    return f"{ADMIN}{org.pk}/"


@pytest.fixture
def anna(org):
    return make_member(org, "Anna", "Beispiel")


def test_haushalt_in_der_akte(admin_token, base, org, anna):
    max_ = make_member(org, "Max", "Beispiel")
    start = today() - datetime.timedelta(days=10)
    with tenant_context(org.pk):
        hh = Household.objects.create(organization=org, name="Familie Beispiel", kind="family")
        for m, role in ((anna, "adult"), (max_, "child")):
            HouseholdMember.objects.create(
                organization=org,
                household=hh,
                membership=m,
                kind="family",
                role=role,
                valid_from=start,
            )
    data = app(admin_token).get(f"{base}members/{anna.pk}/").json()
    [entry] = data["households"]
    assert entry["name"] == "Familie Beispiel"
    assert entry["kind"] == "family"
    assert [o["member_id"] for o in entry["others"]] == [max_.pk]


def test_qualifikationen_nur_lesen(admin_token, base, org, anna):
    with tenant_context(org.pk):
        kind = QualificationType.objects.create(organization=org, name="Erste Hilfe")
        Qualification.objects.create(
            organization=org,
            person=anna.person,
            kind=kind,
            acquired_on=today() - datetime.timedelta(days=700),
            valid_until=today() + datetime.timedelta(days=20),
        )
    c = app(admin_token)
    overview = c.get(f"{base}qualifications/?stand=bald")
    assert overview.status_code == 200, overview.content
    assert [r["kind_name"] for r in overview.json()] == ["Erste Hilfe"]
    records = c.get(f"{base}members/{anna.pk}/qualifications/")
    assert records.status_code == 200, records.content
    assert records.json()[0]["kind_name"] == "Erste Hilfe"
    resp = c.post(
        f"{base}members/{anna.pk}/qualifications/",
        {"kind": kind.pk, "acquired_on": today().isoformat()},
        content_type=JSON,
    )
    assert resp.status_code == 405


def test_qualifikationen_modul_aus(admin_token, base, org, anna):
    org.enabled_modules = [m for m in org.enabled_modules if m != "qualifications"]
    org.save()
    assert app(admin_token).get(f"{base}qualifications/").status_code == 404


def test_fristen_nur_lesen_und_nur_mit_recht(admin_token, base, board, org):
    c = app(admin_token)
    # Schriftführung hat nur members.*: kein Fristenkalender
    assert c.get(f"{base}obligations/").status_code == 403
    give_role(board["user"], org, ["obligations.view"], name="Fristen")
    with tenant_context(org.pk):
        Obligation.objects.create(
            organization=org,
            title="Steuererklärung",
            due_date=today() - datetime.timedelta(days=1),
        )
    resp = c.get(f"{base}obligations/")
    assert resp.status_code == 200, resp.content
    [item] = resp.json()["items"]
    assert (item["title"], item["status"]) == ("Steuererklärung", "overdue")
    assert c.post(f"{base}obligations/", {"title": "Neu"}, content_type=JSON).status_code == 405
