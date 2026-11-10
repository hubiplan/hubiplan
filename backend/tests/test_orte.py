"""Gespeicherte Orte (konzepte/termin-rundschreiben-rueckmeldung.md, O1)."""

import datetime

import pytest
from django.utils import timezone

from events.models import Event
from places.models import Place

from .factories import give_role, make_member, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


def ok(resp, code=(200, 201)):
    assert resp.status_code in ((code,) if isinstance(code, int) else code), resp.content
    return resp.json() if resp.content else None


@pytest.fixture
def setup(orgs, api):
    club = orgs["a"]
    chef = make_user("terminwart@example.org")
    give_role(chef, club, permissions=["events.view", "events.edit"], name="Terminwart")
    reader = make_user("beisitz@example.org")
    give_role(reader, club, permissions=["events.view"], name="Beisitz")
    fed = make_user("bund@example.org")
    give_role(fed, orgs["federation"], permissions=["events.edit"], name="Bundesvorstand")
    other = make_user("andere@example.org")
    give_role(other, orgs["b"], permissions=["events.edit"], name="Terminwart")
    return {
        "club": club,
        "chef": api(chef),
        "reader": api(reader),
        "fed": api(fed),
        "other": api(other),
        "url": f"/api/orgs/{club.pk}/places/",
        "fed_url": f"/api/orgs/{orgs['federation'].pk}/places/",
        "other_url": f"/api/orgs/{orgs['b'].pk}/places/",
    }


def test_speichern_aendern_archivieren_loeschen(setup):
    s = setup
    place = ok(
        s["chef"].post(
            s["url"],
            {
                "name": " Schützenhaus ",
                "address": "Musterweg 1, 12345 Musterstadt",
                "directions": "Parkplatz hinter der Halle",
                "latitude": 51.17,
                "longitude": 6.73,
            },
            content_type=JSON,
        ),
        201,
    )
    assert place["name"] == "Schützenhaus" and place["own"] and place["can_edit"]
    assert place["latitude"] == pytest.approx(51.17)
    # Gleicher Name (ohne Groß/klein) gibt es nur einmal
    dup = s["chef"].post(s["url"], {"name": "schützenhaus"}, content_type=JSON)
    assert dup.status_code == 400
    # Breite ohne Länge geht nicht
    half = s["chef"].post(s["url"], {"name": "Wiese", "latitude": 51}, content_type=JSON)
    assert half.status_code == 400
    ok(s["chef"].patch(f"{s['url']}{place['id']}/", {"is_active": False}, content_type=JSON))
    assert ok(s["chef"].get(s["url"]))["places"] == []
    assert [p["name"] for p in ok(s["chef"].get(f"{s['url']}?alle=1"))["places"]] == [
        "Schützenhaus"
    ]
    ok(s["chef"].delete(f"{s['url']}{place['id']}/"), 204)
    assert not Place.objects.exists()


def test_rechte_und_trennung(setup):
    s = setup
    place = ok(s["chef"].post(s["url"], {"name": "Festplatz"}, content_type=JSON))
    # Lesen darf jede Rolle, speichern nicht
    data = ok(s["reader"].get(s["url"]))
    assert [p["name"] for p in data["places"]] == ["Festplatz"]
    assert not data["can_edit"] and not data["places"][0]["can_edit"]
    assert s["reader"].post(s["url"], {"name": "Halle"}, content_type=JSON).status_code == 403
    assert (
        s["reader"].patch(f"{s['url']}{place['id']}/", {"name": "X"}, content_type=JSON).status_code
        == 403
    )
    # Fremder Verein sieht nichts und kommt nicht an den Ort
    assert ok(s["other"].get(s["other_url"]))["places"] == []
    assert s["other"].get(s["url"]).status_code == 404
    assert (
        s["other"].patch(f"{s['other_url']}{place['id']}/", {"name": "X"}, content_type=JSON)
    ).status_code == 404


def test_orte_des_dachverbands(setup):
    s = setup
    ok(s["fed"].post(s["fed_url"], {"name": "Bundesfestplatz"}, content_type=JSON))
    ok(s["chef"].post(s["url"], {"name": "Schützenhaus"}, content_type=JSON))
    rows = ok(s["chef"].get(s["url"]))["places"]
    # Eigene zuerst, dann die des Dachverbands (nur lesen)
    assert [(p["name"], p["own"], p["can_edit"]) for p in rows] == [
        ("Schützenhaus", True, True),
        ("Bundesfestplatz", False, False),
    ]
    fed_place = rows[1]
    assert fed_place["owner"] == "Testbund"
    assert (
        s["chef"].patch(f"{s['url']}{fed_place['id']}/", {"name": "X"}, content_type=JSON)
    ).status_code == 404
    # Der Dachverband sieht die Orte seiner Vereine nicht
    assert [p["name"] for p in ok(s["fed"].get(s["fed_url"]))["places"]] == ["Bundesfestplatz"]
    # Ein anderer Verein desselben Verbands sieht den Ort des Dachverbands, nicht den von A
    assert [p["name"] for p in ok(s["other"].get(s["other_url"]))["places"]] == ["Bundesfestplatz"]


def test_vorschlaege_aus_bisherigen_eintraegen(setup):
    s = setup
    start = timezone.now() + datetime.timedelta(days=3)
    for _ in range(3):
        Event.objects.create(
            organization=s["club"],
            title="Übungsabend",
            starts_at=start,
            ends_at=start + datetime.timedelta(hours=2),
            location="Schießstand",
            address="Waldweg 3",
        )
    Event.objects.create(
        organization=s["club"],
        title="Einmal",
        starts_at=start,
        ends_at=start + datetime.timedelta(hours=2),
        location="Irgendwo",
    )
    rows = ok(s["chef"].get(f"{s['url']}suggestions/"))
    assert rows == [{"name": "Schießstand", "address": "Waldweg 3", "count": 3}]
    ok(s["chef"].post(s["url"], {"name": "Schießstand"}, content_type=JSON))
    assert ok(s["chef"].get(f"{s['url']}suggestions/")) == []
    assert s["reader"].get(f"{s['url']}suggestions/").status_code == 403


def test_untereinheit_sieht_und_speichert_orte_des_vereins(orgs, api):
    from members.models import DepartmentRoleHolder
    from organizations.models import Department, DepartmentRole
    from portal.models import PortalAccess

    club = orgs["a"]
    club.department_access_enabled = True
    club.member_portal_enabled = True
    club.enabled_modules = sorted({*club.enabled_modules, "members", "events"})
    club.save()
    Place.objects.create(organization=club, name="Schützenhaus")
    zug = Department.objects.create(
        self_managed=True, organization=club, name="Jägerzug", short_name="Jäger"
    )
    max_ = make_member(club, "Max", "Muster", departments=[zug])
    role = DepartmentRole.objects.create(
        department=zug, name="Zugführer", permissions=["dept.events.manage"]
    )
    DepartmentRoleHolder.objects.create(
        organization=club, membership=max_, role=role, valid_from=datetime.date(2020, 1, 1)
    )
    user = make_user("zugfuehrer@example.org")
    PortalAccess.objects.create(organization=club, membership=max_, user=user)
    c = api(user)
    url = f"/api/depts/{zug.pk}/places/"
    data = ok(c.get(url))
    assert [p["name"] for p in data["places"]] == ["Schützenhaus"]
    assert data["can_edit"] and not data["can_manage"]
    assert not data["places"][0]["can_edit"]
    ok(c.post(url, {"name": "Zuglokal"}, content_type=JSON), 201)
    assert Place.objects.get(name="Zuglokal").organization_id == club.pk
    pk = Place.objects.get(name="Schützenhaus").pk
    assert c.patch(f"{url}{pk}/", {"name": "X"}, content_type=JSON).status_code == 403


def test_stand_der_einrichtung(setup):
    s = setup
    items = ok(s["chef"].get(f"/api/orgs/{s['club'].pk}/setup-status/"))["items"]
    assert items["/einstellungen/orte"] == {"required": False, "done": False, "count": 0}
    ok(s["chef"].post(s["url"], {"name": "Festplatz"}, content_type=JSON))
    items = ok(s["chef"].get(f"/api/orgs/{s['club'].pk}/setup-status/"))["items"]
    assert items["/einstellungen/orte"]["done"] is True
    # Ohne Recht dazu kein Punkt
    items = ok(s["reader"].get(f"/api/orgs/{s['club'].pk}/setup-status/"))["items"]
    assert "/einstellungen/orte" not in items
