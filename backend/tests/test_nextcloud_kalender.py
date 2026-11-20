"""Termine per CalDAV in Kalender der Nextcloud schreiben (oidc.nc_calendars). Erfundene Daten."""

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone

from accounts.mfa import encrypt
from core import safehttp
from core.tenancy import rls_bypass
from events.models import Event
from oidc import nc_calendars
from oidc.models import CalendarItem, Client

from .test_nextcloud_anmeldung import CLOUD, make_client

JSON = "application/json"
DAV = f"{CLOUD}/remote.php/dav/calendars/hubiplan-dienst/"


class FakeCalDAV:
    """Nachgebauter CalDAV-Teil der Nextcloud: Kalender, Einträge und Freigaben."""

    def __init__(self):
        self.calendars: dict[str, dict[str, bytes]] = {}
        self.shares: list[tuple[str, bytes]] = []
        self.calls: list[tuple[str, str]] = []
        self.status_put = 201

    def __call__(self, method, url, *, headers=None, body=None, **kwargs):
        assert headers["Authorization"].startswith("Basic ")
        assert url.startswith(DAV), url
        rest = url[len(DAV) :]
        self.calls.append((method, rest))
        uri, _, name = rest.partition("/")
        cal = self.calendars.get(uri)
        if method == "MKCALENDAR":
            if cal is not None:
                return safehttp.Response(405, {}, b"")
            self.calendars[uri] = {}
            return safehttp.Response(201, {}, b"")
        if cal is None:
            return safehttp.Response(404, {}, b"")
        if method == "POST":
            self.shares.append((uri, body))
            return safehttp.Response(200, {}, b"")
        if method == "PUT":
            assert headers["Content-Type"].startswith("text/calendar")
            existed = name in cal
            cal[name] = body
            return safehttp.Response(204 if existed else self.status_put, {}, b"")
        if method == "DELETE":
            if not name:
                del self.calendars[uri]
                return safehttp.Response(204, {}, b"")
            if cal.pop(name, None) is None:
                return safehttp.Response(404, {}, b"")
            return safehttp.Response(204, {}, b"")
        raise AssertionError(method)


@pytest.fixture
def dav(monkeypatch):
    fake = FakeCalDAV()
    monkeypatch.setattr(safehttp, "request", fake)
    return fake


@pytest.fixture
def termine(orgs):
    soon = timezone.now() + datetime.timedelta(days=7)
    with rls_bypass():
        for org in orgs.values():
            org.enabled_modules = ["members", "events"]
            org.save()

        def event(org, title, visibility):
            return Event.objects.create(
                organization=org,
                title=title,
                visibility=visibility,
                starts_at=soon,
                ends_at=soon + datetime.timedelta(hours=2),
            )

        return {
            "fest": event(orgs["a"], "Sommerfest", "public"),
            "probe": event(orgs["a"], "Übungsabend", "members"),
            "sitzung": event(orgs["a"], "Vorstandssitzung", "board"),
            "bund": event(orgs["federation"], "Bundestreffen", "members"),
            "fremd": event(orgs["b"], "Fest B", "members"),
        }


def kalender(org, **extra) -> Client:
    client, _secret = make_client(
        org,
        service_user="hubiplan-dienst",
        service_password=encrypt("app-passwort", purpose="nextcloud"),
        **extra,
    )
    return client


def inhalt(dav, uri) -> str:
    return b"".join(dav.calendars.get(uri, {}).values()).decode()


def test_schreibt_termine_und_vorstand_getrennt_und_gibt_lesend_frei(dav, orgs, termine):
    client = kalender(orgs["a"], calendar_members=True, calendar_board=True)
    result = nc_calendars.sync_client(client.pk)
    assert result["error"] == ""
    members = f"hubiplan-{client.pk}-termine"
    board = f"hubiplan-{client.pk}-vorstand"
    text = inhalt(dav, members)
    assert "Sommerfest" in text and "Übungsabend" in text and "Bundestreffen" in text
    assert "Vorstandssitzung" not in text and "Fest B" not in text
    assert "METHOD:" not in text  # RFC 4791: keine iTIP-Methode in Kalenderobjekten
    board_text = inhalt(dav, board)
    assert "Vorstandssitzung" in board_text and "Sommerfest" not in board_text
    # Freigaben nur lesend an die Gruppen
    shares = {uri: body.decode() for uri, body in dav.shares}
    assert "principals/groups/Mitglieder" in shares[members]
    assert "principals/groups/Vorstand" in shares[board]
    assert "read-write" not in "".join(shares.values())
    with rls_bypass():
        assert CalendarItem.objects.filter(client=client).count() == 4


def test_nur_aenderungen_werden_geschrieben_und_alte_geloescht(dav, orgs, termine):
    client = kalender(orgs["a"], calendar_members=True)
    nc_calendars.sync_client(client.pk)
    dav.calls.clear()
    result = nc_calendars.sync_client(client.pk)
    assert result["members"] == {"written": 0, "deleted": 0, "unchanged": 3}
    assert [c for c in dav.calls if c[0] == "PUT"] == []
    with rls_bypass():
        Event.objects.filter(pk=termine["probe"].pk).update(title="Übungsabend neu")
        Event.objects.filter(pk=termine["fest"].pk).delete()
    result = nc_calendars.sync_client(client.pk)
    assert result["members"] == {"written": 1, "deleted": 1, "unchanged": 1}
    text = inhalt(dav, f"hubiplan-{client.pk}-termine")
    assert "Übungsabend neu" in text and "Sommerfest" not in text


def test_in_der_nextcloud_geloeschter_kalender_wird_neu_gefuellt(dav, orgs, termine):
    client = kalender(orgs["a"], calendar_members=True)
    nc_calendars.sync_client(client.pk)
    del dav.calendars[f"hubiplan-{client.pk}-termine"]
    result = nc_calendars.sync_client(client.pk)
    assert result["members"]["written"] == 3


def test_abschalten_loescht_den_kalender(dav, orgs, termine):
    client = kalender(orgs["a"], calendar_members=True)
    nc_calendars.sync_client(client.pk)
    with rls_bypass():
        Client.objects.filter(pk=client.pk).update(calendar_members=False)
    assert nc_calendars.sync_all() == 1
    assert f"hubiplan-{client.pk}-termine" not in dav.calendars
    with rls_bypass():
        assert not CalendarItem.objects.filter(client=client).exists()
    # Danach gibt es nichts mehr zu tun
    assert nc_calendars.sync_all() == 0


def test_fehler_steht_am_dienst(dav, orgs, termine):
    client = kalender(orgs["a"], calendar_members=True)
    dav.status_put = 507
    result = nc_calendars.sync_client(client.pk)
    assert "507" in result["error"]
    with rls_bypass():
        client.refresh_from_db()
    assert "507" in client.calendar_error and client.calendar_synced_at


def test_ohne_dienstkonto_nicht_einschaltbar(api, orgs, board_a):
    client, _secret = make_client(orgs["a"])
    resp = api(board_a).patch(
        f"/api/orgs/{orgs['a'].pk}/nextcloud/{client.pk}/",
        {"calendar_members": True},
        content_type=JSON,
    )
    assert resp.status_code == 400 and "calendar_members" in resp.json()


def test_vorstandskalender_braucht_bestaetigung(api, orgs, board_a, settings):
    client = kalender(orgs["a"])
    settings.MFA_STEP_UP = True
    url = f"/api/orgs/{orgs['a'].pk}/nextcloud/{client.pk}/"
    resp = api(board_a).patch(url, {"calendar_board": True}, content_type=JSON)
    assert resp.status_code == 403 and resp.json().get("step_up")
    # Termine für Mitglieder brauchen das nicht
    resp = api(board_a).patch(url, {"calendar_members": True}, content_type=JSON)
    assert resp.status_code == 200, resp.content


def test_speichern_stoesst_abgleich_an_und_knopf_gleicht_ab(
    api, dav, orgs, board_a, termine, django_capture_on_commit_callbacks, monkeypatch
):
    from oidc import tasks

    queued = []
    monkeypatch.setattr(
        tasks.sync_client_calendars, "delay", lambda pk, unshare=None: queued.append(pk)
    )
    client = kalender(orgs["a"])
    url = f"/api/orgs/{orgs['a'].pk}/nextcloud/{client.pk}/"
    with django_capture_on_commit_callbacks(execute=True):
        resp = api(board_a).patch(url, {"calendar_members": True}, content_type=JSON)
    assert resp.status_code == 200 and queued == [client.pk]
    resp = api(board_a).post(url + "calendars/")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["result"]["members"]["written"] == 3
    assert body["client"]["calendar_error"] == ""
    # Termine des Dachverbands kommen mit, obwohl die Anfrage im Verein läuft
    assert "Bundestreffen" in inhalt(dav, f"hubiplan-{client.pk}-termine")


def test_andere_gruppe_nimmt_alte_freigabe_zurueck(dav, orgs, termine):
    client = kalender(orgs["a"], calendar_members=True)
    nc_calendars.sync_client(client.pk)
    with rls_bypass():
        Client.objects.filter(pk=client.pk).update(calendar_members_group="Alle Schützen")
    dav.shares.clear()
    nc_calendars.sync_client(client.pk, {"members": "Mitglieder"})
    bodies = [b.decode() for _u, b in dav.shares]
    assert "<o:remove><d:href>principal:principals/groups/Mitglieder<" in bodies[0]
    assert "principals/groups/Alle%20Sch%C3%BCtzen" in bodies[1]
