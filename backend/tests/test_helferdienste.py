"""Helferdienste und Schichtpläne, Schritt H1 (konzepte/helferdienste.md)."""

import datetime
from zoneinfo import ZoneInfo

import pytest
from django.db import connection
from django.utils import timezone

from helpers.models import HelperPlan, ShiftAssignment
from members.models import Person

from .factories import give_role, make_member, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"
BERLIN = ZoneInfo("Europe/Berlin")


def ok(resp, code=(200, 201)):
    assert resp.status_code in ((code,) if isinstance(code, int) else code), resp.content
    return resp.json() if resp.content else None


def day(offset=20):
    return timezone.localdate() + datetime.timedelta(days=offset)


@pytest.fixture
def setup(orgs, api):
    org = orgs["a"]
    org.enabled_modules = sorted({*org.enabled_modules, "helpers", "events"})
    org.save()
    chef = make_user("festwart@example.org")
    give_role(chef, org, permissions=["helpers.edit"], name="Festwart")
    reader = make_user("helfer@example.org")
    give_role(reader, org, permissions=["helpers.view"], name="Beisitz")
    return {
        "org": org,
        "chef": api(chef),
        "reader": api(reader),
        "url": f"/api/orgs/{org.pk}/helpers/",
    }


def new_plan(s, **extra):
    return ok(s["chef"].post(s["url"], {"title": "Schützenfest 2099", **extra}, content_type=JSON))


def test_plan_dienste_schichten_schnelleingabe(setup):
    s = setup
    plan = new_plan(s)
    assert plan["status"] == "draft" and plan["duties"] == []
    duty = ok(
        s["chef"].post(
            f"{s['url']}{plan['id']}/duties/",
            {"name": "Theke Festzelt", "min_age": 18},
            content_type=JSON,
        )
    )
    shifts = ok(
        s["chef"].post(
            f"{s['url']}duties/{duty['id']}/shifts/",
            {"day": day().isoformat(), "quick": "14-18, 18-22, 22-02", "needed": 4},
            content_type=JSON,
        )
    )
    assert len(shifts) == 3
    last = shifts[2]
    start = datetime.datetime.fromisoformat(last["starts_at"]).astimezone(BERLIN)
    end = datetime.datetime.fromisoformat(last["ends_at"]).astimezone(BERLIN)
    assert (start.hour, end.hour) == (22, 2) and end.date() == day() + datetime.timedelta(days=1)
    bad = s["chef"].post(
        f"{s['url']}duties/{duty['id']}/shifts/",
        {"day": day().isoformat(), "quick": "abends"},
        content_type=JSON,
    )
    assert bad.status_code == 400
    data = ok(s["chef"].get(f"{s['url']}{plan['id']}/"))
    assert data["needed"] == 12 and data["open"] == 12
    listing = ok(s["reader"].get(s["url"]))
    assert listing[0]["needed"] == 12 and listing[0]["open"] == 12
    # Nur Lesen
    assert s["reader"].post(s["url"], {"title": "X"}, content_type=JSON).status_code == 403


def test_einteilen_mit_pruefungen(setup):
    s = setup
    org = s["org"]
    anna = make_member(org, "Anna", "Muster", birth_date=datetime.date(1990, 5, 1))
    jan = make_member(org, "Jan", "Jung", birth_date=day() - datetime.timedelta(days=365 * 16))
    plan = new_plan(s)
    theke = ok(
        s["chef"].post(
            f"{s['url']}{plan['id']}/duties/", {"name": "Theke", "min_age": 18}, content_type=JSON
        )
    )
    kasse = ok(
        s["chef"].post(f"{s['url']}{plan['id']}/duties/", {"name": "Kasse"}, content_type=JSON)
    )
    t1 = ok(
        s["chef"].post(
            f"{s['url']}duties/{theke['id']}/shifts/",
            {"day": day().isoformat(), "quick": "14-18", "needed": 1},
            content_type=JSON,
        )
    )[0]
    k1 = ok(
        s["chef"].post(
            f"{s['url']}duties/{kasse['id']}/shifts/",
            {"day": day().isoformat(), "quick": "16-20", "needed": 2},
            content_type=JSON,
        )
    )[0]
    assign = f"{s['url']}shifts/{t1['id']}/assignments/"
    ok(s["chef"].post(assign, {"membership": anna.pk}, content_type=JSON))
    # Doppelt geht nicht
    assert s["chef"].post(assign, {"membership": anna.pk}, content_type=JSON).status_code == 400
    # Voll: erst nach Bestätigung
    resp = s["chef"].post(assign, {"name": "Gerd Gast", "phone": "0170 000000"}, content_type=JSON)
    assert resp.status_code == 400 and resp.json()["warnings"] == ["full"]
    ext = ok(
        s["chef"].post(
            assign, {"name": "Gerd Gast", "phone": "0170 000000", "force": True}, content_type=JSON
        )
    )
    assert ext["external"] and ext["phone"] == "0170 000000"
    # Überschneidung mit der Theke
    resp = s["chef"].post(
        f"{s['url']}shifts/{k1['id']}/assignments/", {"membership": anna.pk}, content_type=JSON
    )
    assert resp.status_code == 400 and resp.json()["warnings"] == ["overlap"]
    assert "Theke" in str(resp.json()["detail"])
    # Mindestalter
    t2 = ok(
        s["chef"].post(
            f"{s['url']}duties/{theke['id']}/shifts/",
            {"day": (day() + datetime.timedelta(days=1)).isoformat(), "quick": "14-18"},
            content_type=JSON,
        )
    )[0]
    resp = s["chef"].post(
        f"{s['url']}shifts/{t2['id']}/assignments/", {"membership": jan.pk}, content_type=JSON
    )
    assert resp.status_code == 400 and resp.json()["warnings"] == ["age"]
    # Lesende sehen Namen, aber keine Telefonnummern
    data = ok(s["reader"].get(f"{s['url']}{plan['id']}/"))
    people = data["duties"][0]["shifts"][0]["assignments"]
    assert [p["name"] for p in people] == ["Anna Muster", "Gerd Gast"]
    assert "phone" not in people[1]
    # Mitgliedersuche nur zum Einteilen
    found = ok(s["chef"].get(f"{s['url']}members/?suche=mus"))
    assert [m["last_name"] for m in found] == ["Muster"]
    assert s["reader"].get(f"{s['url']}members/?suche=mus").status_code == 403
    # Absagen und Löschen
    ok(
        s["chef"].patch(
            f"{s['url']}assignments/{ext['id']}/", {"status": "cancelled"}, content_type=JSON
        )
    )
    assert ok(s["chef"].get(f"{s['url']}{plan['id']}/"))["duties"][0]["shifts"][0]["taken"] == 1
    # Dienst mit Eingeteilten lässt sich nicht löschen
    assert s["chef"].delete(f"{s['url']}duties/{theke['id']}/").status_code == 400
    # Verschlüsselt gespeichert
    with connection.cursor() as cur:
        cur.execute("SELECT name, phone FROM helpers_shiftassignment")
        assert all("Gerd" not in str(n) and "0170" not in str(p) for n, p in cur.fetchall())
    assert ShiftAssignment.objects.count() == 2
    assert Person.objects.filter(pk=anna.person_id).exists()


def test_druck_und_export(setup):
    s = setup
    plan = new_plan(s)
    duty = ok(
        s["chef"].post(f"{s['url']}{plan['id']}/duties/", {"name": "Aufbau"}, content_type=JSON)
    )
    shift = ok(
        s["chef"].post(
            f"{s['url']}duties/{duty['id']}/shifts/",
            {"day": day().isoformat(), "quick": "9-12", "needed": 3},
            content_type=JSON,
        )
    )[0]
    ok(
        s["chef"].post(
            f"{s['url']}shifts/{shift['id']}/assignments/",
            {"name": "Max Muster"},
            content_type=JSON,
        )
    )
    resp = s["reader"].get(f"{s['url']}{plan['id']}/export/")
    assert resp.status_code == 200 and resp.content.startswith(b"%PDF")
    resp = s["reader"].get(f"{s['url']}{plan['id']}/export/?datei=xlsx")
    assert resp.status_code == 200 and resp.content.startswith(b"PK")


def test_status_termin_und_loeschen(setup, orgs, api):
    from events.models import Event

    s = setup
    org = s["org"]
    event = Event.objects.create(
        organization=org,
        title="Schützenfest",
        starts_at=timezone.now() + datetime.timedelta(days=20),
        ends_at=timezone.now() + datetime.timedelta(days=22),
    )
    plan = new_plan(s, event=event.pk)
    assert plan["event_title"] == "Schützenfest"
    events = ok(s["chef"].get(f"{s['url']}events/"))
    assert [e["id"] for e in events] == [event.pk]
    # Termin eines anderen Vereins geht nicht
    other = Event.objects.create(
        organization=orgs["b"],
        title="Fremd",
        starts_at=timezone.now(),
        ends_at=timezone.now(),
    )
    assert (
        s["chef"].post(s["url"], {"title": "X", "event": other.pk}, content_type=JSON).status_code
        == 400
    )
    url = f"{s['url']}{plan['id']}/"
    plan = ok(
        s["chef"].patch(url, {"status": "published", "version": plan["version"]}, content_type=JSON)
    )
    assert s["chef"].patch(url, {"title": "Y", "version": 1}, content_type=JSON).status_code == 409
    assert s["chef"].delete(url).status_code == 400
    plan = ok(s["chef"].patch(url, {"status": "closed"}, content_type=JSON))
    resp = s["chef"].post(f"{url}duties/", {"name": "Theke"}, content_type=JSON)
    assert resp.status_code == 400
    assert s["chef"].delete(url).status_code == 204
    assert not HelperPlan.objects.filter(pk=plan["id"]).exists()


def test_modul_und_untereinheit(orgs, api):
    from members.models import DepartmentRoleHolder
    from organizations.models import Department, DepartmentRole
    from portal.models import PortalAccess

    org = orgs["a"]
    user = make_user("festwart2@example.org")
    give_role(user, org, permissions=["helpers.edit"], name="Festwart")
    client = api(user)
    # Modul aus: nicht vorhanden
    assert client.get(f"/api/orgs/{org.pk}/helpers/").status_code == 404
    org.enabled_modules = sorted({*org.enabled_modules, "members", "helpers", "events"})
    org.department_access_enabled = True
    org.member_portal_enabled = True
    org.save()
    assert client.get(f"/api/orgs/{org.pk}/helpers/").status_code == 200
    # Zug mit eigener Rolle plant eigene Dienste
    zug = Department.objects.create(
        self_managed=True, organization=org, name="Jägerzug", short_name="Jäger"
    )
    andere = Department.objects.create(
        self_managed=True, organization=org, name="Grenadiere", short_name="Gren"
    )
    max_ = make_member(org, "Max", "Muster", departments=[zug])
    make_member(org, "Otto", "Muster", departments=[andere])
    role = DepartmentRole.objects.create(
        department=zug, name="Zugführer", permissions=["helpers.edit"]
    )
    DepartmentRoleHolder.objects.create(
        organization=org, membership=max_, role=role, valid_from=datetime.date(2020, 1, 1)
    )
    zf = make_user("zugfuehrer@example.org")
    PortalAccess.objects.create(organization=org, membership=max_, user=zf)
    c = api(zf)
    url = f"/api/depts/{zug.pk}/helpers/"
    plan = ok(c.post(url, {"title": "Zugfest"}, content_type=JSON))
    assert HelperPlan.objects.get(pk=plan["id"]).department_id == zug.pk
    assert ok(client.get(f"/api/orgs/{org.pk}/helpers/")) == []
    assert [p["title"] for p in ok(c.get(url))] == ["Zugfest"]
    # Einteilen nur aus dem eigenen Zug
    assert [m["first_name"] for m in ok(c.get(f"{url}members/?suche=muster"))] == ["Max"]
    assert c.get(f"/api/depts/{andere.pk}/helpers/").status_code == 404
