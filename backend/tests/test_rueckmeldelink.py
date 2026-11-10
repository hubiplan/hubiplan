"""Rückmeldung per Link aus der Mail, „Vielleicht“ und Bemerkung
(konzepte/termin-rundschreiben-rueckmeldung.md, T2)."""
# ruff: noqa: F811  (Fixtures aus test_m12_events als Parameter)

import re

import pytest
from django.core import mail as djmail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from audit.models import AuditEntry
from events import notify, rsvp_link
from events.models import Event, EventResponse

from .factories import make_member
from .test_m12_events import (  # noqa: F401  (Fixtures)
    JSON,
    cal,
    create,
    org_base,
    private_root,
    zug,
    zug2,
)
from .test_rundschreiben import send

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup(cal, board_a, zug, api, private_root):
    club = cal["a"]
    anna = make_member(club, "Anna", "Adler", departments=[zug])
    bernd = make_member(club, "Bernd", "Berg", departments=[zug])
    c = api(board_a)
    base = org_base(club)
    ev = create(
        c,
        base,
        title="Sommerfest",
        location="Festplatz",
        rsvp_enabled=True,
        rsvp_capacity=1,
        rsvp_guests=True,
        rsvp_maybe=True,
        rsvp_note=True,
        rsvp_note_question="  Essenswunsch?  ",
        rsvp_deadline="2099-06-10T18:00:00",
        starts_at="2099-06-13T14:00:00",
        ends_at="2099-06-13T18:00:00",
    )
    return {"club": club, "c": c, "base": base, "ev": ev, "anna": anna, "bernd": bernd}


def link_of(text: str) -> str:
    return re.search(r"/rueckmeldung/(\S+)", text).group(1)


def test_einladung_mit_link_und_anhang(setup, settings):
    s = setup
    assert s["ev"]["rsvp"]["note_question"] == "Essenswunsch?"
    resp = s["c"].post(
        f"{s['base']}events/{s['ev']['id']}/attachments/",
        {"file": SimpleUploadedFile("Plan.pdf", b"%PDF-1.4 erfunden", "application/pdf")},
    )
    assert resp.status_code == 201
    djmail.outbox.clear()
    assert notify.send(s["ev"]["id"], notify.INVITE) == 2
    anna = next(m for m in djmail.outbox if m.to == ["anna@example.org"])
    assert "Zu- oder absagen (ohne Anmeldung):" in anna.body
    assert "Anlagen: Plan.pdf" in anna.body
    assert anna.attachments[0][0] == "Plan.pdf"
    token = link_of(anna.body)
    assert rsvp_link.parse(token) == (s["ev"]["id"], s["anna"].pk)

    public = Client()
    page = public.get(f"/api/public/rsvp/{token}/")
    assert page.status_code == 200, page.content
    data = page.json()
    assert page["Cache-Control"] == "no-store"
    assert data["first_name"] == "Anna" and data["event"]["title"] == "Sommerfest"
    assert data["rsvp"]["can_respond"] and data["rsvp"]["mine"] is None
    assert data["rsvp"]["maybe_allowed"] and data["rsvp"]["note_question"] == "Essenswunsch?"
    # Öffnen allein speichert nichts
    assert not EventResponse.objects.exists()
    att = data["attachments"][0]
    assert public.get(att["url"]).status_code == 200

    # Zusage mit Bemerkung, dann Änderung auf „Vielleicht“
    saved = public.post(
        f"/api/public/rsvp/{token}/", {"status": "yes", "note": "Vegetarisch"}, content_type=JSON
    )
    assert saved.status_code == 200, saved.content
    r = EventResponse.objects.get()
    assert (r.status, r.note, r.source) == ("yes", "Vegetarisch", "link")
    saved = public.post(f"/api/public/rsvp/{token}/", {"status": "maybe"}, content_type=JSON)
    assert saved.json()["rsvp"]["mine"]["status"] == "maybe"
    assert any("(Mail-Link)" in key for e in AuditEntry.objects.all() for key in (e.changes or {}))

    # „Vielleicht“ zählt nicht gegen die Höchstzahl: Bernd bekommt den einen Platz
    bernd = rsvp_link.token(s["ev"]["id"], s["bernd"].pk)
    ok = public.post(f"/api/public/rsvp/{bernd}/", {"status": "yes"}, content_type=JSON)
    assert ok.status_code == 200, ok.content
    full = public.post(f"/api/public/rsvp/{token}/", {"status": "yes"}, content_type=JSON)
    assert full.status_code == 400

    # Liste des Vorstands zählt „Vielleicht“ eigens
    lst = s["c"].get(f"{s['base']}events/{s['ev']['id']}/responses/").json()
    assert lst["summary"]["maybe"] == 1 and lst["summary"]["yes"] == 1
    assert lst["summary"]["no"] == 0


def test_ungueltige_und_fremde_links(setup, cal):
    s = setup
    public = Client()
    assert public.get("/api/public/rsvp/kaputt/").status_code == 404
    # Nicht eingeladen (anderer Verein)
    other = make_member(cal["b"], "Olga", "Ort")
    token = rsvp_link.token(s["ev"]["id"], other.pk)
    assert public.get(f"/api/public/rsvp/{token}/").status_code == 404
    # Anhang eines anderen Termins nicht über diesen Link
    token = rsvp_link.token(s["ev"]["id"], s["anna"].pk)
    assert public.get(f"/api/public/rsvp/{token}/attachments/999999/").status_code == 404
    # Nach dem Anmeldeschluss nur noch lesen
    Event.objects.filter(pk=s["ev"]["id"]).update(
        rsvp_deadline="2000-01-01T00:00:00Z",
    )
    data = public.get(f"/api/public/rsvp/{token}/").json()
    assert data["rsvp"]["can_respond"] is False
    resp = public.post(f"/api/public/rsvp/{token}/", {"status": "yes"}, content_type=JSON)
    assert resp.status_code == 400


def test_vielleicht_und_bemerkung_nur_wenn_erlaubt(setup):
    s = setup
    s["c"].patch(
        f"{s['base']}events/{s['ev']['id']}/",
        {"rsvp_maybe": False, "rsvp_note": False},
        content_type=JSON,
    )
    event = Event.objects.get(pk=s["ev"]["id"])
    assert event.rsvp_note_question == ""
    token = rsvp_link.token(event.pk, s["anna"].pk)
    public = Client()
    resp = public.post(f"/api/public/rsvp/{token}/", {"status": "maybe"}, content_type=JSON)
    assert resp.status_code == 400
    resp = public.post(
        f"/api/public/rsvp/{token}/", {"status": "no", "note": "Geht nicht"}, content_type=JSON
    )
    assert resp.status_code == 200
    assert EventResponse.objects.get().note == ""


def test_rundschreiben_zum_termin_mit_link(setup, settings, django_capture_on_commit_callbacks):
    s = setup
    url = f"/api/orgs/{s['club'].pk}/circulars/"
    draft = s["c"].post(f"{url}from-event/{s['ev']['id']}/", content_type=JSON).json()
    result = send(s["c"], url, draft["id"], django_capture_on_commit_callbacks, settings)
    assert result["sent"]["mail"] == 2
    anna = next(m for m in djmail.outbox if m.to == ["anna@example.org"])
    token = link_of(anna.body)
    assert rsvp_link.parse(token) == (s["ev"]["id"], s["anna"].pk)
    html = anna.alternatives[0][0]
    assert "/rueckmeldung/" in html


def test_erinnerung_auch_an_vielleicht(setup):
    s = setup
    event = Event.objects.get(pk=s["ev"]["id"])
    EventResponse.objects.create(
        organization=s["club"], event=event, membership=s["anna"], status="maybe", source="member"
    )
    names = {m.person.first_name for m in notify.recipients(event, notify.REMIND)}
    assert names == {"Anna"}
