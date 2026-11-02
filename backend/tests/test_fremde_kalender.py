"""Fremde Kalender: Termine aus Vereinsplaner und iCal-Abos (nur lesbare Kopien).

Alle Antworten von außen sind erfunden; ``events.external._get`` wird ersetzt.
"""

import datetime
import json

import pytest
from django.utils import timezone

from events import external
from events.models import Event, ExternalCalendar
from events.tasks import sync_external_calendars

from .factories import give_role, make_user
from .test_m12_events import member_with_access, org_base, titles

pytestmark = pytest.mark.django_db
JSON = "application/json"


def soon(days: int, hour: int = 18) -> datetime.datetime:
    day = timezone.localdate() + datetime.timedelta(days=days)
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time(hour)))


def vp_event(uuid, title, days=10, **extra):
    start = soon(days)
    return {
        "uuid": uuid,
        "title": title,
        "description": "Erfundener Termin",
        "start": start.isoformat(),
        "end": (start + datetime.timedelta(hours=3)).isoformat(),
        "full_day": False,
        "category_name": "Versammlung",
        "location": {
            "display_name": "Festzelt",
            "city_name": "Musterstadt",
            "zip_code": "12345",
            "street": "Am Markt",
            "house_number": "1",
        },
        "owner_name": "Vorstand",
        "register_until": None,
        "is_recurring": False,
        **extra,
    }


class FakeRemote:
    """Erfundene Gegenstelle: Vereinsplaner-Seiten und iCal-Texte."""

    def __init__(self):
        self.vp_events = []
        self.vp_status = 206
        self.ical = ""
        self.calls = []

    def __call__(self, url, headers, max_body):
        self.calls.append((url, headers))
        if url.startswith(external.VEREINSPLANER_URL):
            if self.vp_status in (401, 403):
                return self.vp_status, json.dumps({"success": False, "message": "nein"}).encode()
            page = int(url.split("page=")[1].split("&")[0])
            per = 2  # klein, damit mehrere Seiten entstehen
            chunk = self.vp_events[(page - 1) * per : page * per]
            last = max(1, -(-len(self.vp_events) // per))
            body = {
                "success": True,
                "data": chunk,
                "pagination": {
                    "current_page": page,
                    "per_page": per,
                    "total": len(self.vp_events),
                    "last_page": last,
                },
            }
            return self.vp_status, json.dumps(body).encode()
        return 200, self.ical.encode()


@pytest.fixture
def remote(monkeypatch):
    fake = FakeRemote()
    monkeypatch.setattr(external, "_get", fake)
    return fake


@pytest.fixture
def cal(orgs):
    for org in orgs.values():
        org.enabled_modules = ["members", "events"]
        org.member_portal_enabled = True
        org.save()
    return orgs


def add(client, org, **data):
    payload = {"name": "BSV Musterstadt", "kind": "vereinsplaner", "token": "tok-erfunden", **data}
    resp = client.post(f"{org_base(org)}events/external/", payload, content_type=JSON)
    assert resp.status_code == 201, resp.json()
    return resp.json()


def window_titles(client, org):
    frm = (timezone.localdate() - datetime.timedelta(days=30)).isoformat()
    to = (timezone.localdate() + datetime.timedelta(days=300)).isoformat()
    return titles(client, org_base(org), frm, to)


class TestVereinsplaner:
    def test_anlegen_holt_alle_seiten(self, cal, board_a, api, remote):
        remote.vp_events = [
            vp_event(f"0000000{i}-aaaa", f"Termin {i}", days=i + 1) for i in range(5)
        ]
        data = add(api(board_a), cal["a"])
        assert data["event_count"] == 5 and data["last_error"] == ""
        assert data["has_token"] and "token" not in data
        assert len([c for c in remote.calls if "page=" in c[0]]) == 3
        url, headers = remote.calls[0]
        assert headers["x-api-token"] == "tok-erfunden" and "x-api-secret" not in headers
        ev = Event.objects.get(title="Termin 0")
        assert ev.location == "Festzelt" and ev.address == "Am Markt 1, 12345 Musterstadt"
        assert "Kategorie: Versammlung" in ev.description
        assert ev.remote_uid.startswith(f"ext:{data['id']}:")
        assert window_titles(api(board_a), cal["a"])[:2] == ["Termin 0", "Termin 1"]

    def test_token_verschluesselt_und_nicht_im_protokoll(self, cal, board_a, api, remote):
        from audit.models import AuditEntry

        add(api(board_a), cal["a"], secret="geheim-erfunden")
        stored = ExternalCalendar.objects.get()
        assert "tok-erfunden" not in stored.token and "geheim" not in stored.secret
        assert remote.calls[0][1]["x-api-secret"] == "geheim-erfunden"
        dump = json.dumps([e.changes for e in AuditEntry.objects.all()], default=str)
        assert "tok-erfunden" not in dump and stored.token not in dump

    def test_kopien_nicht_bearbeitbar(self, cal, board_a, api, remote):
        remote.vp_events = [vp_event("u1", "Kreisfest")]
        add(api(board_a), cal["a"])
        ev = Event.objects.get(title="Kreisfest")
        c = api(board_a)
        detail = c.get(f"{org_base(cal['a'])}events/{ev.pk}/").json()
        assert detail["can_edit"] is False and detail["can_hide"] is True
        assert detail["source"]["name"] == "BSV Musterstadt"
        resp = c.patch(f"{org_base(cal['a'])}events/{ev.pk}/", {"title": "x"}, content_type=JSON)
        assert resp.status_code == 403

    def test_abgleich_aendert_und_entfernt(self, cal, board_a, api, remote):
        remote.vp_events = [vp_event("u1", "Kreisfest"), vp_event("u2", "Weg damit")]
        data = add(api(board_a), cal["a"])
        remote.vp_events = [vp_event("u1", "Kreisfest neu", days=12)]
        resp = api(board_a).post(f"{org_base(cal['a'])}events/external/{data['id']}/sync/")
        assert resp.status_code == 200 and resp.json()["event_count"] == 1
        ev = Event.objects.get()
        assert ev.title == "Kreisfest neu" and ev.changed_at is not None

    def test_fehler_behaelt_letzten_stand(self, cal, board_a, api, remote):
        remote.vp_events = [vp_event("u1", "Kreisfest")]
        data = add(api(board_a), cal["a"])
        remote.vp_status = 401
        resp = api(board_a).post(f"{org_base(cal['a'])}events/external/{data['id']}/sync/")
        assert "lehnt das Token ab" in resp.json()["last_error"]
        assert Event.objects.filter(title="Kreisfest").exists()

    def test_ausblenden_und_wieder_zeigen(self, cal, board_a, api, remote):
        remote.vp_events = [vp_event("u1", "Kreisfest"), vp_event("u2", "Andere")]
        data = add(api(board_a), cal["a"])
        c = api(board_a)
        ev = Event.objects.get(title="Kreisfest")
        assert c.post(f"{org_base(cal['a'])}events/{ev.pk}/hide/").status_code == 204
        c.post(f"{org_base(cal['a'])}events/external/{data['id']}/sync/")
        assert window_titles(c, cal["a"]) == ["Andere"]
        hidden = c.get(f"{org_base(cal['a'])}events/external/").json()[0]["hidden"]
        assert [h["title"] for h in hidden] == ["Kreisfest"]
        resp = c.post(
            f"{org_base(cal['a'])}events/external/{data['id']}/show/",
            {"key": hidden[0]["key"]},
            content_type=JSON,
        )
        assert resp.status_code == 200 and resp.json()["hidden"] == []
        assert sorted(window_titles(c, cal["a"])) == ["Andere", "Kreisfest"]

    def test_sichtbarkeit_und_loeschen(self, cal, board_a, api, remote):
        remote.vp_events = [vp_event("u1", "Kreisfest")]
        data = add(api(board_a), cal["a"], visibility="board")
        _, user, access = member_with_access(cal["a"], "Mia")
        frm = timezone.localdate().isoformat()
        to = (timezone.localdate() + datetime.timedelta(days=60)).isoformat()
        portal = f"/api/portal/{access.pk}/events/?from={frm}&to={to}"
        assert api(user).get(portal).json()["items"] == []
        c = api(board_a)
        c.patch(
            f"{org_base(cal['a'])}events/external/{data['id']}/",
            {"visibility": "members"},
            content_type=JSON,
        )
        items = api(user).get(portal).json()["items"]
        assert [i["title"] for i in items] == ["Kreisfest"]
        assert items[0]["source"] == "BSV Musterstadt"
        assert c.delete(f"{org_base(cal['a'])}events/external/{data['id']}/").status_code == 204
        assert not Event.objects.exists()

    def test_nur_mit_terminrecht_und_nur_eigene(self, cal, board_a, board_b, api, remote):
        data = add(api(board_a), cal["a"])
        assert api(board_b).get(f"{org_base(cal['a'])}events/external/").status_code == 404
        assert (
            api(board_b).delete(f"{org_base(cal['b'])}events/external/{data['id']}/").status_code
            == 404
        )
        reader = make_user("leser@example.org")
        give_role(reader, cal["a"], permissions=["members.view"], name="Leser")
        assert api(reader).get(f"{org_base(cal['a'])}events/external/").status_code == 403

    def test_stuendlicher_abruf(self, cal, board_a, api, remote):
        add(api(board_a), cal["a"])
        remote.vp_events = [vp_event("u9", "Später dazu")]
        assert sync_external_calendars() == 1
        assert Event.objects.filter(title="Später dazu").exists()


ICS = """BEGIN:VCALENDAR\r
VERSION:2.0\r
PRODID:-//Erfunden//DE\r
BEGIN:VEVENT\r
UID:einmal@example.org\r
DTSTART;TZID=Europe/Berlin:{d1}T190000\r
DTEND;TZID=Europe/Berlin:{d1}T210000\r
SUMMARY:Vorstandssitzung\\, offen\r
LOCATION:Vereinsheim\r
DESCRIPTION:Erste Zeile\\nzweite Zeile mit langem Text, der gefaltet\r
  wird\r
BEGIN:VALARM\r
ACTION:DISPLAY\r
DESCRIPTION:nicht übernehmen\r
END:VALARM\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:serie@example.org\r
DTSTART;VALUE=DATE:{d2}\r
DTEND;VALUE=DATE:{d2b}\r
RRULE:FREQ=WEEKLY;COUNT=3\r
SUMMARY:Schießabend\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:serie@example.org\r
RECURRENCE-ID;VALUE=DATE:{d3}\r
DTSTART;VALUE=DATE:{d3}\r
DTEND;VALUE=DATE:{d3b}\r
SUMMARY:Schießabend fällt aus\r
STATUS:CANCELLED\r
END:VEVENT\r
END:VCALENDAR\r
"""


def ics_text():
    def d(n):
        return (timezone.localdate() + datetime.timedelta(days=n)).strftime("%Y%m%d")

    return ICS.format(d1=d(5), d2=d(3), d2b=d(4), d3=d(10), d3b=d(11))


class TestIcal:
    def test_parse(self):
        items = external.parse_ical(ics_text())
        assert [i.title for i in items] == [
            "Schießabend",
            "Vorstandssitzung, offen",
            "Schießabend fällt aus",
            "Schießabend",
        ]
        sitzung = items[1]
        assert sitzung.description == (
            "Erste Zeile\nzweite Zeile mit langem Text, der gefaltet wird"
        )
        assert sitzung.location == "Vereinsheim" and not sitzung.all_day
        assert timezone.localtime(sitzung.starts_at).hour == 19
        abend = items[0]
        assert abend.all_day and abend.starts_at == abend.ends_at
        assert items[2].is_cancelled
        assert len({i.key for i in items}) == 4

    def test_ueber_link(self, cal, board_a, api, remote):
        remote.ical = ics_text()
        data = add(
            api(board_a), cal["a"], kind="ical", token="webcal://kalender.example.org/abo.ics"
        )
        assert data["event_count"] == 4, data
        assert remote.calls[-1][0] == "https://kalender.example.org/abo.ics"

    def test_link_muss_https_sein(self, cal, board_a, api, remote):
        resp = api(board_a).post(
            f"{org_base(cal['a'])}events/external/",
            {"name": "X", "kind": "ical", "token": "http://kalender.example.org/a.ics"},
            content_type=JSON,
        )
        assert resp.status_code == 400

    def test_kein_kalender(self, cal, board_a, api, remote):
        remote.ical = "<html>Anmeldung</html>"
        data = add(api(board_a), cal["a"], kind="ical", token="https://x.example.org/a.ics")
        assert "kein Kalender" in data["last_error"]
