"""Versammlungen und Sitzungen, Schritt V1 (konzepte/versammlungen.md)."""

import datetime
from zoneinfo import ZoneInfo

import pytest
from django.db import connection
from django.utils import timezone

from events.models import Event
from meetings.models import AgendaItem, Meeting, MeetingKind
from members.models import DepartmentRoleHolder
from organizations.models import Department, DepartmentRole
from portal.models import PortalAccess

from .factories import give_role, make_member, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"
BERLIN = ZoneInfo("Europe/Berlin")


def at(days, hour):
    day = timezone.localdate() + datetime.timedelta(days=days)
    return datetime.datetime.combine(day, datetime.time(hour), BERLIN).isoformat()


def ok(resp, code=(200, 201)):
    assert resp.status_code in ((code,) if isinstance(code, int) else code), resp.content
    return resp.json() if resp.content else None


@pytest.fixture
def setup(orgs, api):
    org = orgs["a"]
    org.enabled_modules = sorted({*org.enabled_modules, "meetings", "events"})
    org.save()
    chef = make_user("vorsitz@example.org")
    give_role(chef, org, permissions=["meetings.edit"], name="Vorsitz")
    reader = make_user("beisitz@example.org")
    give_role(reader, org, permissions=["meetings.view"], name="Beisitz")
    return {
        "org": org,
        "chef": api(chef),
        "reader": api(reader),
        "url": f"/api/orgs/{org.pk}/meetings/",
    }


def kind_named(client, url, name):
    return next(k for k in ok(client.get(url + "kinds/")) if k["name"] == name)


def new_meeting(s, name="Jahreshauptversammlung", **extra):
    kind = kind_named(s["chef"], s["url"], name)
    payload = {"kind": kind["id"], "starts_at": at(30, 19), "ends_at": at(30, 22), **extra}
    return ok(s["chef"].post(s["url"], payload, content_type=JSON), 201)


def test_voreingestellte_arten_und_tagesordnung(setup):
    s = setup
    kinds = ok(s["reader"].get(s["url"] + "kinds/"))
    assert [k["name"] for k in kinds] == [
        "Jahreshauptversammlung",
        "Außerordentliche Mitgliederversammlung",
        "Vorstandssitzung",
    ]
    meeting = new_meeting(s, location="Schützenhaus")
    assert meeting["title"] == "Jahreshauptversammlung"
    assert meeting["status"] == "draft"
    titles = [a["title"] for a in meeting["agenda"]]
    assert titles[0].startswith("Begrüßung") and "Entlastung des Vorstands" in titles
    assert [a["position"] for a in meeting["agenda"]] == list(range(1, len(titles) + 1))
    # Einladungsfrist 14 Tage vor dem Termin
    start = datetime.date.fromisoformat(at(30, 19)[:10])
    assert meeting["invite_by"] == (start - datetime.timedelta(days=14)).isoformat()
    # Der Termin steht im Kalender
    event = Event.objects.get(pk=meeting["event"])
    assert event.location == "Schützenhaus" and event.visibility == "members"


def test_vorstandssitzung_nur_fuer_vorstand_im_kalender(setup):
    meeting = new_meeting(setup, "Vorstandssitzung")
    assert Event.objects.get(pk=meeting["event"]).visibility == "board"
    assert len(meeting["agenda"]) == 3


def test_tagesordnung_aus_letzter_versammlung(setup):
    s = setup
    first = new_meeting(s)
    items = [
        {"id": first["agenda"][0]["id"], "title": "Begrüßung", "type": "other"},
        {"title": "Ehrungen", "description": "25 Jahre Mitgliedschaft", "type": "other"},
    ]
    saved = ok(
        s["chef"].put(
            f"{s['url']}{first['id']}/agenda/",
            {"version": first["version"], "items": items},
            content_type=JSON,
        )
    )
    assert [a["title"] for a in saved["agenda"]] == ["Begrüßung", "Ehrungen"]
    assert saved["agenda"][0]["id"] == first["agenda"][0]["id"]
    second = new_meeting(s)
    assert [(a["title"], a["description"]) for a in second["agenda"]] == [
        ("Begrüßung", ""),
        ("Ehrungen", "25 Jahre Mitgliedschaft"),
    ]
    # Veralteter Stand wird abgelehnt
    stale = s["chef"].put(
        f"{s['url']}{first['id']}/agenda/",
        {"version": first["version"], "items": items},
        content_type=JSON,
    )
    assert stale.status_code == 409


def test_inhalte_verschluesselt(setup):
    s = setup
    meeting = new_meeting(s)
    ok(
        s["chef"].patch(
            f"{s['url']}{meeting['id']}/",
            {"chair": "Erika Beispiel", "note": "Saal reservieren"},
            content_type=JSON,
        )
    )
    with connection.cursor() as cur:
        cur.execute("SELECT chair, note FROM meetings_meeting WHERE id = %s", [meeting["id"]])
        chair, note = cur.fetchone()
        cur.execute("SELECT title FROM meetings_agendaitem WHERE meeting_id = %s", [meeting["id"]])
        titles = [r[0] for r in cur.fetchall()]
    assert "Erika" not in chair and "Saal" not in note
    assert not any("Begrüßung" in t for t in titles)
    assert ok(s["reader"].get(f"{s['url']}{meeting['id']}/"))["chair"] == "Erika Beispiel"


def test_nur_mit_recht_und_modul(setup, orgs, api):
    s = setup
    meeting = new_meeting(s)
    kind = kind_named(s["chef"], s["url"], "Vorstandssitzung")
    payload = {"kind": kind["id"], "starts_at": at(3, 19), "ends_at": at(3, 21)}
    assert s["reader"].post(s["url"], payload, content_type=JSON).status_code == 403
    assert (
        s["reader"]
        .patch(f"{s['url']}{meeting['id']}/", {"title": "x"}, content_type=JSON)
        .status_code
        == 403
    )
    nobody = make_user("mitglied@example.org")
    give_role(nobody, s["org"], permissions=["events.view"], name="Mitglied")
    assert api(nobody).get(s["url"]).status_code == 403
    # Fremder Verein sieht nichts
    other = make_user("fremd@example.org")
    give_role(other, orgs["b"], permissions=["meetings.edit"], name="Vorsitz")
    orgs["b"].enabled_modules = ["meetings"]
    orgs["b"].save()
    assert ok(api(other).get(f"/api/orgs/{orgs['b'].pk}/meetings/")) == []
    assert api(other).get(f"/api/orgs/{orgs['b'].pk}/meetings/{meeting['id']}/").status_code == 404
    # Modul aus: nicht erreichbar
    s["org"].enabled_modules = ["members"]
    s["org"].save()
    assert s["chef"].get(s["url"]).status_code == 404


def test_absagen_und_loeschen(setup, board_a, api):
    s = setup
    meeting = new_meeting(s)
    url = f"{s['url']}{meeting['id']}/"
    cancelled = ok(s["chef"].patch(url, {"status": "cancelled"}, content_type=JSON))
    assert cancelled["status"] == "cancelled"
    assert Event.objects.get(pk=meeting["event"]).is_cancelled
    # Der Termin lässt sich nicht im Kalender löschen, nur über die Versammlung
    give_role(board_a, s["org"], permissions=["events.edit"], name="Termine")
    event_url = f"/api/orgs/{s['org'].pk}/events/{meeting['event']}/"
    assert api(board_a).delete(event_url).status_code == 400
    assert s["chef"].delete(url).status_code == 204
    assert not Meeting.objects.filter(pk=meeting["id"]).exists()
    assert not Event.objects.filter(pk=meeting["event"]).exists()
    assert not AgendaItem.objects.filter(meeting_id=meeting["id"]).exists()


def test_nach_einladung_nur_absagen(setup):
    s = setup
    meeting = new_meeting(s)
    Meeting.objects.filter(pk=meeting["id"]).update(status="invited")
    url = f"{s['url']}{meeting['id']}/"
    assert s["chef"].delete(url).status_code == 400
    assert s["chef"].patch(url, {"status": "draft"}, content_type=JSON).status_code == 400
    assert ok(s["chef"].patch(url, {"status": "cancelled"}, content_type=JSON))


def test_arten_bearbeiten(setup):
    s = setup
    from members.models import MemberType

    aktiv = MemberType.objects.create(organization=s["org"], name="aktiv")
    kind = ok(
        s["chef"].post(
            s["url"] + "kinds/",
            {"name": "Festausschuss", "base": "committee", "invite_days": 5},
            content_type=JSON,
        ),
        201,
    )
    assert kind["invite_days"] == 5 and not kind["used"]
    dup = s["chef"].post(s["url"] + "kinds/", {"name": "Festausschuss"}, content_type=JSON)
    assert dup.status_code == 400
    changed = ok(
        s["chef"].patch(
            f"{s['url']}kinds/{kind['id']}/",
            {"voter_types": [aktiv.pk], "voter_min_age": 16, "quorum_percent": 10},
            content_type=JSON,
        )
    )
    assert changed["voter_types"] == [aktiv.pk] and changed["quorum_percent"] == 10
    bad = s["chef"].patch(
        f"{s['url']}kinds/{kind['id']}/", {"voter_types": [999999]}, content_type=JSON
    )
    assert bad.status_code == 400
    jhv = kind_named(s["chef"], s["url"], "Jahreshauptversammlung")
    new_meeting(s)
    assert s["chef"].delete(f"{s['url']}kinds/{jhv['id']}/").status_code == 400
    assert s["chef"].delete(f"{s['url']}kinds/{kind['id']}/").status_code == 204
    assert not MeetingKind.objects.filter(pk=kind["id"]).exists()


def test_zugversammlung(orgs, api):
    club = orgs["a"]
    club.enabled_modules = ["members", "meetings", "events"]
    club.department_access_enabled = True
    club.member_portal_enabled = True
    club.save()
    zug = Department.objects.create(
        self_managed=True, organization=club, name="Jägerzug", short_name="Jäger"
    )
    andere = Department.objects.create(
        self_managed=True, organization=club, name="Grenadiere", short_name="Gren"
    )
    max_ = make_member(club, "Max", "Muster", departments=[zug])
    role = DepartmentRole.objects.create(
        department=zug, name="Zugführer", permissions=["meetings.edit"]
    )
    DepartmentRoleHolder.objects.create(
        organization=club, membership=max_, role=role, valid_from=datetime.date(2020, 1, 1)
    )
    user = make_user("zugfuehrer@example.org")
    PortalAccess.objects.create(organization=club, membership=max_, user=user)
    c = api(user)
    url = f"/api/depts/{zug.pk}/meetings/"
    kinds = ok(c.get(url + "kinds/"))
    assert [k["name"] for k in kinds] == ["Versammlung", "Sitzung der Leitung"]
    meeting = ok(
        c.post(
            url,
            {"kind": kinds[0]["id"], "starts_at": at(10, 20), "ends_at": at(10, 22)},
            content_type=JSON,
        ),
        201,
    )
    event = Event.objects.get(pk=meeting["event"])
    assert event.department_id == zug.pk
    # Andere Untereinheit und Verein sehen die Zugversammlung nicht
    assert c.get(f"/api/depts/{andere.pk}/meetings/").status_code == 404
    chef = make_user("vorsitz@example.org")
    give_role(chef, club, permissions=["meetings.edit"], name="Vorsitz")
    assert ok(api(chef).get(f"/api/orgs/{club.pk}/meetings/")) == []
    # Arten des Vereins sind im Zug nicht wählbar
    club_kind = kind_named(api(chef), f"/api/orgs/{club.pk}/meetings/", "Vorstandssitzung")
    bad = c.post(
        url,
        {"kind": club_kind["id"], "starts_at": at(10, 20), "ends_at": at(10, 22)},
        content_type=JSON,
    )
    assert bad.status_code == 400
