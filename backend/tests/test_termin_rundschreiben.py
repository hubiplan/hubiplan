"""Rundschreiben zu einem Termin (konzepte/termin-rundschreiben-rueckmeldung.md, T1)."""
# ruff: noqa: F811  (Fixtures aus test_m12_events als Parameter)

import pytest
from django.core import mail as djmail
from django.core.files.uploadedfile import SimpleUploadedFile

from circulars.models import Circular
from events.models import Event, EventResponse

from .factories import give_role, make_member, make_user
from .test_m12_events import (  # noqa: F401  (Fixtures)
    JSON,
    cal,
    create,
    dept_role,
    member_with_access,
    org_base,
    private_root,
    zug,
    zug2,
)
from .test_rundschreiben import preview, send

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup(cal, board_a, zug, zug2, api, private_root):
    club = cal["a"]
    people = {
        "anna": make_member(club, "Anna", "Adler", departments=[zug]),
        "bernd": make_member(club, "Bernd", "Berg", departments=[zug]),
        "clara": make_member(club, "Clara", "Christ", departments=[zug2]),
    }
    c = api(board_a)
    base = org_base(club)
    ev = create(
        c,
        base,
        title="Königsschießen",
        location="Schießstand",
        address="Waldweg 3",
        description="Mit Grillen.",
        rsvp_enabled=True,
        rsvp_deadline="2026-06-10T18:00:00",
        starts_at="2026-06-13T14:00:00",
        ends_at="2026-06-13T18:00:00",
    )
    return {"club": club, "c": c, "base": base, "ev": ev, "zug": zug, **people}


def from_event(s, event_id=None):
    url = f"/api/orgs/{s['club'].pk}/circulars/"
    resp = s["c"].post(f"{url}from-event/{event_id or s['ev']['id']}/", content_type=JSON)
    return url, resp


def test_entwurf_aus_termin_an_die_eingeladenen(
    setup, settings, django_capture_on_commit_callbacks
):
    s = setup
    for name, kind in (("Termin.pdf", "application/pdf"), ("Plan.png", "image/png")):
        content = b"%PDF-1.4 erfunden" if kind == "application/pdf" else b"\x89PNG\r\n\x1a\nxx"
        resp = s["c"].post(
            f"{s['base']}events/{s['ev']['id']}/attachments/",
            {"file": SimpleUploadedFile(name, content, kind)},
        )
        assert resp.status_code == 201, resp.content
    url, resp = from_event(s)
    assert resp.status_code == 201, resp.content
    data = resp.json()
    assert data["event"]["id"] == s["ev"]["id"] and data["event"]["rsvp_enabled"]
    assert data["subject"] == "Königsschießen am 13.06.2026"
    assert "Wo: Schießstand, Waldweg 3" in data["body"] and "Mit Grillen." in data["body"]
    assert "bis 10.06.2026" in data["body"]
    assert data["kind"] == "notice"
    assert [a["name"] for a in data["attachments"]] == ["Termin.pdf"]
    assert data["skipped_attachments"] == ["Plan.png"]
    # Die Eingeladenen des Vereinstermins
    names = {i["first_name"] for i in preview(s["c"], url, data["id"])["items"]}
    assert names == {"Anna", "Bernd", "Clara"}
    # Am Termin: Rundschreiben verlinkt
    ev = s["c"].get(f"{s['base']}events/{s['ev']['id']}/").json()
    assert ev["can_circular"] is True
    assert [c["id"] for c in ev["circulars"]] == [data["id"]]
    # Versand mit dem Anhang des Termins
    result = send(s["c"], url, data["id"], django_capture_on_commit_callbacks, settings)
    assert result["sent"]["mail"] == 3
    anna = next(m for m in djmail.outbox if m.to == ["anna@example.org"])
    assert anna.attachments[0][0] == "Termin.pdf"


def test_nur_bestimmte_rueckmeldungen(setup):
    s = setup
    event = Event.objects.get(pk=s["ev"]["id"])
    EventResponse.objects.create(
        organization=s["club"], event=event, membership=s["anna"], status="yes", source="member"
    )
    url, resp = from_event(s)
    pk = resp.json()["id"]
    s["c"].patch(f"{url}{pk}/", {"filters": {"event_responses": ["open"]}}, content_type=JSON)
    assert {i["first_name"] for i in preview(s["c"], url, pk)["items"]} == {"Bernd", "Clara"}
    s["c"].patch(f"{url}{pk}/", {"filters": {"event_responses": ["yes", "x"]}}, content_type=JSON)
    assert Circular.objects.get(pk=pk).filters == {"event_responses": ["yes"]}
    assert {i["first_name"] for i in preview(s["c"], url, pk)["items"]} == {"Anna"}
    # Kopie bleibt beim Termin
    copy = s["c"].post(url, {"copy_of": pk}, content_type=JSON).json()
    assert copy["event"]["id"] == s["ev"]["id"]


def test_rechte_und_grenzen(setup, cal, api):
    s = setup
    # Vorstandstermin: keine Eingeladenen, kein Rundschreiben dazu
    board_only = create(s["c"], s["base"], title="Vorstandssitzung", visibility="board")
    assert from_event(s, board_only["id"])[1].status_code == 404
    ev = s["c"].get(f"{s['base']}events/{board_only['id']}/").json()
    assert ev["can_circular"] is False
    # Fremder Verein
    url = f"/api/orgs/{cal['b'].pk}/circulars/"
    user = make_user("vorstand-b2@example.org")
    give_role(user, cal["b"])
    resp = api(user).post(f"{url}from-event/{s['ev']['id']}/", content_type=JSON)
    assert resp.status_code == 404


def test_untereinheit_schreibt_zu_eigenem_termin(cal, zug, zug2, api, private_root):
    club = cal["a"]
    leader, user, _ = member_with_access(club, "Zora", depts=[zug])
    dept_role(zug, leader, ["dept.events.manage", "dept.circulars.send", "dept.members.view"])
    make_member(club, "Anna", "Adler", departments=[zug])
    c = api(user)
    base = f"/api/depts/{zug.pk}/"
    ev = create(c, base, title="Zugabend", rsvp_enabled=True)
    data = c.get(f"{base}events/{ev['id']}/").json()
    assert data["can_circular"] is True
    resp = c.post(f"{base}circulars/from-event/{ev['id']}/", content_type=JSON)
    assert resp.status_code == 201, resp.content
    circular = Circular.objects.get(pk=resp.json()["id"])
    assert circular.department_id == zug.pk and circular.event_id == ev["id"]
    names = {i["first_name"] for i in preview(c, f"{base}circulars/", circular.pk)["items"]}
    assert names == {"Zora", "Anna"}


def test_erinnerung_an_alle_ohne_rueckmeldung(setup):
    s = setup
    event = Event.objects.get(pk=s["ev"]["id"])
    EventResponse.objects.create(
        organization=s["club"], event=event, membership=s["anna"], status="yes", source="member"
    )
    url = f"/api/orgs/{s['club'].pk}/circulars/"
    resp = s["c"].post(f"{url}from-event/{event.pk}/", {"reminder": True}, content_type=JSON)
    assert resp.status_code == 201, resp.content
    data = resp.json()
    assert data["subject"].startswith("Erinnerung: Königsschießen")
    assert "fehlt uns noch eine Rückmeldung" in data["body"]
    assert data["filters"] == {"event_responses": ["open"]}
    assert {i["first_name"] for i in preview(s["c"], url, data["id"])["items"]} == {
        "Bernd",
        "Clara",
    }
