"""Versammlungen V7: Anmelden per App (wechselnder Code), Teilnahme aus der Ferne und
Online-Abstimmung (offen und geheim, mit Vollmachten). Erfundene Daten."""

import pytest
from django.db import connection

from access.models import Role
from meetings import live
from meetings.models import Attendance, Ballot, Meeting, Poll, VoteCast
from members.models import MemberType
from portal.models import PortalAccess

from .factories import make_member, make_user
from .test_versammlungen import JSON, kind_named, new_meeting, ok, setup  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def world(setup, api):  # noqa: F811
    s = setup
    org = s["org"]
    org.member_portal_enabled = True
    org.save(update_fields=["member_portal_enabled"])
    Role.objects.filter(organization=org, name="Vorsitz").update(
        permissions=["meetings.edit", "members.view"]
    )
    aktiv, _ = MemberType.objects.get_or_create(organization=org, name="aktiv")
    passiv = MemberType.objects.create(organization=org, name="passiv")
    kind = kind_named(s["chef"], s["url"], "Jahreshauptversammlung")
    ok(
        s["chef"].patch(
            f"{s['url']}kinds/{kind['id']}/",
            {"voter_types": [aktiv.pk], "proxies_allowed": True, "online_voting": True},
            content_type=JSON,
        )
    )
    people = {}
    for first, last, mtype in (
        ("Anna", "Muster", aktiv),
        ("Bernd", "Beispiel", aktiv),
        ("Carla", "Probe", aktiv),
        ("Dora", "Passiv", passiv),
    ):
        email = f"{first.lower()}@example.org"
        member = make_member(org, first, last, member_type=mtype, email=email)
        user = make_user(email)
        access = PortalAccess.objects.create(organization=org, membership=member, user=user)
        people[first] = {
            "member": member,
            "client": api(user),
            "url": f"/api/portal/{access.pk}/meetings/",
        }
    meeting = new_meeting(s)
    Meeting.objects.filter(pk=meeting["id"]).update(status="invited")
    item = next(a for a in meeting["agenda"] if a["type"] == "resolution")
    election = next(a for a in meeting["agenda"] if a["type"] == "election")
    return {
        **s,
        "kind": kind,
        "people": people,
        "meeting": meeting,
        "item": item,
        "election": election,
        "live": f"{s['url']}{meeting['id']}/live/",
        "polls": f"{s['url']}{meeting['id']}/polls/",
    }


def checkin(w, who, **body):
    p = w["people"][who]
    return p["client"].post(
        f"{p['url']}{w['meeting']['id']}/live/checkin/", body, content_type=JSON
    )


def member_live(w, who):
    p = w["people"][who]
    return p["client"].get(f"{p['url']}{w['meeting']['id']}/live/")


def test_anmelden_mit_wechselndem_code(world, monkeypatch):
    w = world
    # Geschlossen: nichts zu sehen, kein Anmelden
    assert member_live(w, "Anna").status_code == 404
    data = ok(w["chef"].get(w["live"]))
    assert data["checkin_open"] is False and "code" not in data
    data = ok(w["chef"].post(w["live"], {"open": True}, content_type=JSON))
    code = data["code"]
    assert 1 <= data["refresh_in"] <= live.WINDOW
    # Falscher Code wird abgelehnt
    assert checkin(w, "Anna", code="0-falsch").status_code == 400
    data = ok(checkin(w, "Anna", code=code))
    assert data["status"] == "present" and data["mode"] == "app" and data["voter"]
    # Nichtstimmberechtigte kommen als Gast
    ok(checkin(w, "Dora", code=code))
    att = ok(w["chef"].get(f"{w['url']}{w['meeting']['id']}/attendance/"))
    assert att["present"] == 1 and att["guests"] == 1
    anna = next(r for r in att["rows"] if r["name"] == "Anna Muster")
    assert anna["mode"] == "app"
    # Nach zwei Zeitfenstern gilt der Code nicht mehr
    now = live.time.time()
    monkeypatch.setattr(live.time, "time", lambda: now + 2 * live.WINDOW + 1)
    assert checkin(w, "Bernd", code=code).status_code == 400
    # Ich gehe: zählt nicht mehr, Vollmachten fallen weg
    bernd = Attendance.objects.create(
        organization=w["org"],
        meeting_id=w["meeting"]["id"],
        membership=w["people"]["Bernd"]["member"],
        name="Bernd Beispiel",
        status="represented",
        represented_by=Attendance.objects.get(membership=w["people"]["Anna"]["member"]),
        voter=True,
    )
    p = w["people"]["Anna"]
    data = ok(p["client"].post(f"{p['url']}{w['meeting']['id']}/live/leave/"))
    assert data["status"] == "left"
    bernd.refresh_from_db()
    assert bernd.status == "excused" and bernd.represented_by is None
    # Schließen macht alte Codes ungültig
    ok(w["chef"].post(w["live"], {"open": False}, content_type=JSON))
    assert Meeting.objects.get(pk=w["meeting"]["id"]).checkin_key == ""


def test_teilnahme_aus_der_ferne_nur_wenn_erlaubt(world):
    w = world
    resp = w["chef"].post(w["live"], {"open": True, "remote": True}, content_type=JSON)
    assert resp.status_code == 400
    ok(
        w["chef"].patch(
            f"{w['url']}kinds/{w['kind']['id']}/", {"remote_allowed": True}, content_type=JSON
        )
    )
    data = ok(w["chef"].post(w["live"], {"open": True, "remote": True}, content_type=JSON))
    assert data["remote"] is True
    # Liste im Mitgliederbereich zeigt den Weg
    upcoming = ok(w["people"]["Carla"]["client"].get(w["people"]["Carla"]["url"]))["upcoming"]
    assert upcoming[0]["remote"] is True
    data = ok(checkin(w, "Carla", remote=True))
    assert data["mode"] == "online"
    # Nichtstimmberechtigte nicht aus der Ferne
    assert checkin(w, "Dora", remote=True).status_code == 400
    att = ok(w["chef"].get(f"{w['url']}{w['meeting']['id']}/attendance/"))
    assert att["online"] == 1 and att["present"] == 1


def start_poll(w, item, **body):
    data = ok(w["chef"].post(w["polls"], {"agenda_item": item["id"], **body}, content_type=JSON))
    poll = next(p for p in data["polls"] if p["status"] == "draft")
    ok(w["chef"].post(f"{w['polls']}{poll['id']}/", {"action": "open"}, content_type=JSON))
    return poll


def vote(w, who, poll, choices):
    """choices: Liste von Antworten (Beschriftung) je Stimme in der Reihenfolge der App."""
    p = w["people"][who]
    state = ok(member_live(w, who))
    row = next(x for x in state["polls"] if x["id"] == poll["id"])
    by_label = {o["label"]: o["id"] for o in row["options"]}
    votes = [
        {"attendance": v["attendance"], "option": by_label[c]}
        for v, c in zip(row["votes"], choices, strict=True)
    ]
    return p["client"].post(
        f"{p['url']}{w['meeting']['id']}/polls/{poll['id']}/vote/",
        {"votes": votes},
        content_type=JSON,
    )


def test_geheime_abstimmung_mit_vollmacht(world):
    w = world
    code = ok(w["chef"].post(w["live"], {"open": True}, content_type=JSON))["code"]
    ok(checkin(w, "Anna", code=code))
    ok(checkin(w, "Carla", code=code))
    ok(checkin(w, "Dora", code=code))
    anna_att = Attendance.objects.get(membership=w["people"]["Anna"]["member"])
    ok(
        w["chef"].post(
            f"{w['url']}{w['meeting']['id']}/attendance/",
            {
                "membership": w["people"]["Bernd"]["member"].pk,
                "status": "represented",
                "represented_by": anna_att.pk,
            },
            content_type=JSON,
        )
    )
    # Nur bei Beschluss und Wahl
    report = next(a for a in w["meeting"]["agenda"] if a["type"] == "report")
    resp = w["chef"].post(w["polls"], {"agenda_item": report["id"]}, content_type=JSON)
    assert resp.status_code == 400
    poll = start_poll(w, w["item"], question="Entlastung des Vorstands", secret=True)
    state = ok(member_live(w, "Anna"))
    row = state["polls"][0]
    assert [v["how"] for v in row["votes"]] == ["own", "proxy"] and row["result"] is None
    # Gäste haben keine Stimme
    assert (
        ok(member_live(w, "Dora"))["polls"] == []
        or not ok(member_live(w, "Dora"))["polls"][0]["votes"]
    )
    ok(vote(w, "Anna", poll, ["Ja", "Nein"]))
    assert vote(w, "Anna", poll, ["Ja", "Ja"]).status_code == 400  # schon abgestimmt
    ok(vote(w, "Carla", poll, ["Ja"]))
    data = ok(w["chef"].get(w["live"]))
    assert data["polls"][0]["cast"] == 3 and data["polls"][0]["result"] is None
    data = ok(w["chef"].post(f"{w['polls']}{poll['id']}/", {"action": "close"}, content_type=JSON))
    result = {r["label"]: r["votes"] for r in data["polls"][0]["result"]}
    assert result == {"Ja": 2, "Nein": 1, "Enthaltung": 0}
    assert data["polls"][0]["entitled"] == 3 and "open_votes" not in data["polls"][0]
    # Geheim: Stimmzettel ohne Person, nur „hat abgestimmt“ getrennt davon
    assert set(Ballot.objects.values_list("attendance", flat=True)) == {None}
    assert VoteCast.objects.filter(poll_id=poll["id"]).count() == 3
    # Nach dem Ende keine Stimmen mehr
    assert vote(w, "Carla", poll, ["Nein"]).status_code == 400
    # Ergebnis in den Beschluss
    ok(w["chef"].post(f"{w['polls']}{poll['id']}/", {"action": "apply"}, content_type=JSON))
    detail = ok(w["chef"].get(f"{w['url']}{w['meeting']['id']}/"))
    item = next(a for a in detail["agenda"] if a["id"] == w["item"]["id"])
    r = item["resolutions"][0]
    assert (r["votes_yes"], r["votes_no"], r["votes_abstain"], r["result"]) == (
        2,
        1,
        0,
        "accepted",
    )
    # Frage verschlüsselt gespeichert
    with connection.cursor() as cur:
        cur.execute("SELECT question FROM meetings_poll")
        assert all("Entlastung" not in str(v) for (v,) in cur.fetchall())


def test_offene_wahl_mit_mehreren_personen(world):
    w = world
    code = ok(w["chef"].post(w["live"], {"open": True}, content_type=JSON))["code"]
    for who in ("Anna", "Bernd", "Carla"):
        ok(checkin(w, who, code=code))
    poll = start_poll(
        w,
        w["election"],
        question="Wahl zum 1. Vorsitzenden",
        office="1. Vorsitzender",
        candidates=[
            {"name": "Anna Muster", "membership": w["people"]["Anna"]["member"].pk},
            {"name": "Bernd Beispiel"},
        ],
    )
    ok(vote(w, "Anna", poll, ["Anna Muster"]))
    ok(vote(w, "Bernd", poll, ["Anna Muster"]))
    ok(vote(w, "Carla", poll, ["Enthaltung"]))
    data = ok(w["chef"].post(f"{w['polls']}{poll['id']}/", {"action": "close"}, content_type=JSON))
    votes = {v["name"]: v["option"] for v in data["polls"][0]["open_votes"]}
    assert votes == {
        "Anna Muster": "Anna Muster",
        "Bernd Beispiel": "Anna Muster",
        "Carla Probe": "Enthaltung",
    }
    ok(w["chef"].post(f"{w['polls']}{poll['id']}/", {"action": "apply"}, content_type=JSON))
    detail = ok(w["chef"].get(f"{w['url']}{w['meeting']['id']}/"))
    item = next(a for a in detail["agenda"] if a["id"] == w["election"]["id"])
    r = item["resolutions"][0]
    assert r["kind"] == "election" and r["elected_name"] == "Anna Muster"
    assert r["office"] == "1. Vorsitzender" and r["votes_yes"] == 2 and r["votes_abstain"] == 1
    assert r["elected"] == w["people"]["Anna"]["member"].pk


def test_wahl_einer_person_und_rechte(world):
    w = world
    poll_url = w["polls"]
    # Ohne Online-Abstimmung an der Art keine Abstimmung
    ok(
        w["chef"].patch(
            f"{w['url']}kinds/{w['kind']['id']}/", {"online_voting": False}, content_type=JSON
        )
    )
    resp = w["chef"].post(poll_url, {"agenda_item": w["election"]["id"]}, content_type=JSON)
    assert resp.status_code == 400
    ok(
        w["chef"].patch(
            f"{w['url']}kinds/{w['kind']['id']}/", {"online_voting": True}, content_type=JSON
        )
    )
    # Wahl ohne Person geht nicht
    resp = w["chef"].post(poll_url, {"agenda_item": w["election"]["id"]}, content_type=JSON)
    assert resp.status_code == 400
    poll = start_poll(
        w, w["election"], office="Kassierer", candidates=[{"name": "Carla Probe"}], secret=True
    )
    assert [o["label"] for o in poll["options"]] == ["Ja", "Nein", "Enthaltung"]
    # Nur Lesen: keine Abstimmungen
    Role.objects.filter(organization=w["org"], name="Beisitz").update(
        permissions=["meetings.view", "members.view"]
    )
    assert w["reader"].get(w["live"]).status_code == 403
    assert (
        w["reader"]
        .post(f"{poll_url}{poll['id']}/", {"action": "close"}, content_type=JSON)
        .status_code
        == 403
    )
    # Gestartete Abstimmung lässt sich nicht löschen, ein Entwurf schon
    assert w["chef"].delete(f"{poll_url}{poll['id']}/").status_code == 400
    draft = ok(
        w["chef"].post(
            poll_url,
            {"agenda_item": w["item"]["id"], "question": "Beitrag"},
            content_type=JSON,
        )
    )["polls"]
    draft = next(p for p in draft if p["status"] == "draft")
    ok(w["chef"].delete(f"{poll_url}{draft['id']}/"))
    assert not Poll.objects.filter(pk=draft["id"]).exists()
    # Abgeschlossene Versammlung: keine Anmeldung, keine Abstimmung
    Meeting.objects.filter(pk=w["meeting"]["id"]).update(status="done")
    assert w["chef"].post(w["live"], {"open": True}, content_type=JSON).status_code == 400
    assert member_live(w, "Anna").status_code == 404
