"""Videoraum am Termin über Nextcloud Talk (oidc.nc_talk)."""

from __future__ import annotations

import datetime
import json
from urllib.parse import parse_qs, urlsplit

import pytest
from django.utils import timezone

from accounts.mfa import encrypt
from core import safehttp
from core.tenancy import rls_bypass
from events import ical, notify
from events.models import Event
from events.recurrence import Occurrence
from oidc import nc_talk
from oidc.models import Client, TalkRoom

from .factories import give_role, make_user
from .test_nextcloud_anmeldung import CLOUD, JSON, make_client

API = "/ocs/v2.php/apps/spreed/api/v4/room"


class FakeTalk:
    """Räume der Talk-Schnittstelle (OCS), so weit HUBIplan sie braucht."""

    def __init__(self):
        self.rooms: dict[str, dict] = {}
        self.fail_password = False
        self.down = False

    def _ocs(self, data, status=200, code=200):
        body = json.dumps({"ocs": {"meta": {"statuscode": code}, "data": data}}).encode()
        return safehttp.Response(status, {}, body)

    def __call__(self, method, url, *, headers=None, body=None, **kwargs):
        assert headers["Authorization"].startswith("Basic ")
        assert headers["OCS-APIRequest"] == "true"
        if self.down:
            return safehttp.Response(503, {}, b"")
        parts = urlsplit(url)
        assert parts.path.startswith(API), parts.path
        query = {k: v[0] for k, v in parse_qs(parts.query).items()}
        rest = parts.path[len(API) :].strip("/").split("/")
        if method == "POST" and rest == [""]:
            token = f"raum{len(self.rooms) + 1}"
            self.rooms[token] = {"type": int(query["roomType"]), "name": query["roomName"]}
            return self._ocs({"token": token})
        token = rest[0]
        if token not in self.rooms:
            return self._ocs({}, 404, 404)
        if method == "PUT" and rest[1:] == ["password"]:
            if self.fail_password:
                return self._ocs({"message": "Passwort zu schwach"}, 400, 400)
            self.rooms[token]["password"] = query["password"]
            return self._ocs({})
        if method == "PUT" and rest[1:] == ["description"]:
            self.rooms[token]["description"] = query["description"]
            return self._ocs({})
        if method == "DELETE" and rest[1:] == []:
            del self.rooms[token]
            return self._ocs({})
        raise AssertionError((method, rest))


@pytest.fixture
def talk(monkeypatch):
    fake = FakeTalk()
    monkeypatch.setattr(safehttp, "request", fake)
    return fake


@pytest.fixture
def sitzung(orgs):
    soon = timezone.now() + datetime.timedelta(days=7)
    with rls_bypass():
        org = orgs["a"]
        org.enabled_modules = ["members", "events"]
        org.save()
        return Event.objects.create(
            organization=org,
            title="Vorstandssitzung",
            visibility="board",
            starts_at=soon,
            ends_at=soon + datetime.timedelta(hours=2),
        )


def talk_client(org, **extra) -> Client:
    client, _ = make_client(
        org,
        service_user="hubiplan-dienst",
        service_password=encrypt("app-passwort", purpose="nextcloud"),
        talk_enabled=True,
        **extra,
    )
    return client


def test_passwort_erfuellt_strenge_regeln():
    for _ in range(20):
        pw = nc_talk.new_password()
        assert len(pw) == 16
        assert any(c.isupper() for c in pw) and any(c.islower() for c in pw)
        assert any(c.isdigit() for c in pw) and any(c in "-_+" for c in pw)


def test_anlegen_und_entfernen_ueber_den_termin(api, orgs, board_a, talk, sitzung):
    talk_client(orgs["a"])
    url = f"/api/orgs/{orgs['a'].pk}/events/{sitzung.pk}/"
    c = api(board_a)
    data = c.get(url).json()
    assert data["video"] is None and data["video_available"] is True
    resp = c.post(url + "video/", {}, content_type=JSON)
    assert resp.status_code == 201, resp.content
    video = resp.json()["video"]
    assert video["url"] == f"{CLOUD}/call/raum1"
    room = talk.rooms["raum1"]
    # Öffentlicher Link mit Passwort, Name mit Datum
    assert room["type"] == 3 and room["password"] == video["password"]
    assert room["name"].startswith("Vorstandssitzung (")
    # Zweimal anlegen gibt denselben Raum
    assert c.post(url + "video/", {}, content_type=JSON).json()["video"]["url"].endswith("raum1")
    assert len(talk.rooms) == 1
    # Liste trägt den Raum mit
    start = timezone.localdate()
    listing = c.get(
        f"/api/orgs/{orgs['a'].pk}/events/?from={start}&to={start + datetime.timedelta(days=30)}"
    ).json()
    item = next(i for i in listing["items"] if i["event_id"] == sitzung.pk)
    assert item["video"]["url"].endswith("/call/raum1")
    resp = c.delete(url + "video/")
    assert resp.status_code == 200 and resp.json()["video"] is None
    assert talk.rooms == {}
    with rls_bypass():
        assert not TalkRoom.objects.exists()


def test_ohne_talk_kein_videoraum(api, orgs, board_a, talk, sitzung):
    talk_client(orgs["a"], is_active=False)
    url = f"/api/orgs/{orgs['a'].pk}/events/{sitzung.pk}/"
    assert api(board_a).get(url).json()["video_available"] is False
    resp = api(board_a).post(url + "video/", {}, content_type=JSON)
    assert resp.status_code == 400 and talk.rooms == {}


def test_nur_wer_den_termin_bearbeitet(api, orgs, talk, sitzung):
    talk_client(orgs["a"])
    leser = make_user("leser@example.org")
    give_role(leser, orgs["a"], ["events.view"], name="Lesen")
    url = f"/api/orgs/{orgs['a'].pk}/events/{sitzung.pk}/video/"
    assert api(leser).post(url, {}, content_type=JSON).status_code in (403, 404)
    assert talk.rooms == {}


def test_ohne_passwort_kein_raum(api, orgs, board_a, talk, sitzung):
    talk_client(orgs["a"])
    talk.fail_password = True
    url = f"/api/orgs/{orgs['a'].pk}/events/{sitzung.pk}/video/"
    resp = api(board_a).post(url, {}, content_type=JSON)
    assert resp.status_code == 400
    # Halb angelegter Raum ist wieder weg
    assert talk.rooms == {}
    with rls_bypass():
        assert not TalkRoom.objects.exists()


def test_link_in_mail_und_nextcloud_kalender_nie_im_abo(orgs, board_a, talk, sitzung):
    talk_client(orgs["a"])
    with rls_bypass():
        room = nc_talk.create(sitzung, board_a)
    password = nc_talk.password_of(room)
    text = notify.body(sitzung, notify.INVITE, "Erika", None)
    assert f"Videoraum: {CLOUD}/call/raum1" in text and password in text
    occ = Occurrence(sitzung, sitzung.starts_at, sitzung.starts_at, sitzung.ends_at, False)
    video = nc_talk.rooms_for([occ])
    caldav = ical.calendar("x", [occ], "h", caldav=True, video=video).decode()
    assert "/call/raum1" in caldav.replace("\r\n ", "")
    abo = ical.calendar("x", [occ], "h").decode()
    assert "call/raum1" not in abo


def test_raeume_gehen_nach_dem_termin(orgs, board_a, talk, sitzung):
    client = talk_client(orgs["a"], talk_keep_days=3)
    with rls_bypass():
        nc_talk.create(sitzung, board_a)
    end = sitzung.ends_at
    assert nc_talk.purge_due(end + datetime.timedelta(days=2)) == 0
    assert nc_talk.purge_due(end + datetime.timedelta(days=4)) == 1
    assert talk.rooms == {}
    # Gelöschter Termin: Raum geht beim nächsten Aufräumen
    with rls_bypass():
        other = Event.objects.create(
            organization=orgs["a"],
            title="Online-Treffen",
            starts_at=sitzung.starts_at,
            ends_at=sitzung.ends_at,
        )
        nc_talk.create(other, board_a)
        other.delete()
    assert nc_talk.purge_due() == 1 and talk.rooms == {}
    # Nextcloud nicht erreichbar: Eintrag bleibt für den nächsten Versuch
    with rls_bypass():
        nc_talk.create(sitzung, board_a)
    talk.down = True
    assert nc_talk.purge_due(end + datetime.timedelta(days=4)) == 0
    with rls_bypass():
        assert TalkRoom.objects.filter(client=client).count() == 1


def test_einschalten_braucht_dienstkonto(api, orgs, board_a):
    client, _ = make_client(orgs["a"])
    url = f"/api/orgs/{orgs['a'].pk}/nextcloud/{client.pk}/"
    resp = api(board_a).patch(url, {"talk_enabled": True}, content_type=JSON)
    assert resp.status_code == 400 and "talk_enabled" in resp.json()
    resp = api(board_a).patch(
        url,
        {"service_user": "hubiplan-dienst", "service_password": "geheim-123", "talk_enabled": True},
        content_type=JSON,
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["talk_enabled"] is True and resp.json()["talk_keep_days"] == 7


def test_fremder_videolink_bis_ein_raum_da_ist(api, orgs, board_a, talk, sitzung):
    talk_client(orgs["a"])
    with rls_bypass():
        Event.objects.filter(pk=sitzung.pk).update(video_url="https://meet.example.org/vorstand")
    url = f"/api/orgs/{orgs['a'].pk}/events/{sitzung.pk}/"
    c = api(board_a)
    video = c.get(url).json()["video"]
    assert video["url"] == "https://meet.example.org/vorstand" and video["talk"] is False
    sitzung.refresh_from_db()
    assert "Videoraum: https://meet.example.org/vorstand" in notify.body(
        sitzung, notify.INVITE, "Erika", None
    )
    video = c.post(url + "video/", {}, content_type=JSON).json()["video"]
    assert video["url"] == f"{CLOUD}/call/raum1" and video["talk"] is True
