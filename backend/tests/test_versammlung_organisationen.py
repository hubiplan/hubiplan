"""Organisationsmitglieder in Versammlungen (Konzept juristische Personen, J4)."""
# ruff: noqa: F811  (Fixture setup aus test_versammlungen als Parameter)

import datetime

import pytest

from core.tenancy import tenant_context
from meetings.models import Attendance
from members import services as member_services
from members.models import ContactPerson, MemberType

from .factories import make_member
from .test_versammlungen import JSON, kind_named, new_meeting, ok, setup  # noqa: F401

pytestmark = pytest.mark.django_db


def make_org_member(org, member_type, name="Musterbau GmbH"):
    with tenant_context(org.pk):
        return member_services.admit(
            org,
            {
                "kind": "organization",
                "member_type": member_type,
                "entry_date": datetime.date(2015, 1, 1),
                "last_name": name,
                "email": "info@musterbau.example",
                "street": "Musterstraße 1",
                "postal_code": "12345",
                "city": "Musterstadt",
            },
        )


@pytest.fixture
def lage(setup):
    from access.models import Role

    s = setup
    org = s["org"]
    Role.objects.filter(organization=org, name="Vorsitz").update(
        permissions=["meetings.edit", "members.view"]
    )
    aktiv, _ = MemberType.objects.get_or_create(organization=org, name="aktiv")
    anna = make_member(org, "Anna", "Muster", member_type=aktiv)
    kind_mitglied = make_member(
        org, "Klara", "Klein", member_type=aktiv, birth_date=datetime.date.today()
    )
    firma = make_org_member(org, aktiv)
    erika = ContactPerson.objects.create(
        organization=org, membership=firma, person=anna.person, is_primary=True
    )
    ContactPerson.objects.create(
        organization=org, membership=firma, last_name="Zwei", represents=False
    )
    kind = kind_named(s["chef"], s["url"], "Jahreshauptversammlung")
    ok(
        s["chef"].patch(
            f"{s['url']}kinds/{kind['id']}/",
            {"voter_types": [aktiv.pk], "voter_min_age": 16, "quorum_count": 2},
            content_type=JSON,
        )
    )
    meeting = new_meeting(s)
    return {
        **s,
        "anna": anna,
        "klein": kind_mitglied,
        "firma": firma,
        "erika": erika,
        "att": f"{s['url']}{meeting['id']}/attendance/",
        "meeting": meeting,
    }


def test_organisation_stimmberechtigt_ohne_mindestalter(lage):
    data = ok(lage["chef"].get(lage["att"]))
    rows = {r["membership"]: r for r in data["rows"]}
    assert data["voters"] == 2  # Anna und die Firma, nicht das Kind
    assert lage["klein"].pk not in rows
    firma = rows[lage["firma"].pk]
    assert firma["kind"] == "organization" and firma["name"] == "Musterbau GmbH"
    # Nur Ansprechpartner mit „vertritt in Versammlungen“
    assert [d["name"] for d in firma["delegates"]] == ["Anna Muster"]
    assert firma["delegates"][0]["membership"] == lage["anna"].pk


def test_durch_vertreter_eine_stimme(lage):
    c, url = lage["chef"], lage["att"]
    data = ok(
        c.post(
            url,
            {"membership": lage["firma"].pk, "status": "delegate", "delegate": lage["erika"].pk},
            content_type=JSON,
        )
    )
    assert data["present"] == 1
    data = ok(c.post(url, {"membership": lage["anna"].pk, "status": "present"}, content_type=JSON))
    # Anna zählt zusätzlich mit eigener Stimme; Hinweis, kein Verbot
    assert data["present"] == 2 and data["quorum"]["reached"]
    anna = next(r for r in data["rows"] if r["membership"] == lage["anna"].pk)
    assert anna["also_represents"] == ["Musterbau GmbH"]
    record = Attendance.objects.get(membership=lage["firma"])
    assert record.delegate_name == "Anna Muster"
    assert record.delegate_membership_id == lage["anna"].pk


def test_freier_name_und_nur_fuer_organisationen(lage):
    c, url = lage["chef"], lage["att"]
    # Ohne Vertreter geht es nicht
    resp = c.post(url, {"membership": lage["firma"].pk, "status": "delegate"}, content_type=JSON)
    assert resp.status_code == 400
    data = ok(
        c.post(
            url,
            {"membership": lage["firma"].pk, "status": "delegate", "delegate_name": "Otto Prokura"},
            content_type=JSON,
        )
    )
    firma = next(r for r in data["rows"] if r["membership"] == lage["firma"].pk)
    assert firma["delegate_name"] == "Otto Prokura"
    # Personen können nicht „durch Vertreter“ anwesend sein
    resp = c.post(
        url,
        {"membership": lage["anna"].pk, "status": "delegate", "delegate_name": "X"},
        content_type=JSON,
    )
    assert resp.status_code == 400
    # Wechsel auf „anwesend“ löscht den Vertreter
    ok(c.post(url, {"membership": lage["firma"].pk, "status": "excused"}, content_type=JSON))
    assert Attendance.objects.get(membership=lage["firma"]).delegate_name == ""


def test_protokoll_nennt_vertreter(lage):
    from meetings.minutes import _attendance_line
    from meetings.models import Meeting

    ok(
        lage["chef"].post(
            lage["att"],
            {"membership": lage["firma"].pk, "status": "delegate", "delegate_name": "Otto Prokura"},
            content_type=JSON,
        )
    )
    with tenant_context(lage["org"].pk):
        line = _attendance_line(Meeting.objects.get(pk=lage["meeting"]["id"]))
    assert "1 Stimmberechtigte anwesend" in line
    assert "Durch Vertreter anwesend: Musterbau GmbH (Otto Prokura)." in line
