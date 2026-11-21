"""Gruppen der Nextcloud laufend abgleichen, nicht nur beim Anmelden (oidc.nc_groups)."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from django.core import mail

from accounts.mfa import encrypt
from core import safehttp
from core.tenancy import rls_bypass
from oidc import nc_groups
from oidc.models import Account, Client

from .factories import give_role, make_user
from .test_nextcloud_anmeldung import (  # noqa: F401
    JSON,
    _key,
    code_of,
    make_client,
    redeem,
    start,
    verify_jwt,
)
from .test_nextcloud_konten import end_roles, login


class FakeGroups:
    """Nachgebaute Benutzer- und Gruppenschnittstelle der Nextcloud (OCS)."""

    def __init__(self):
        self.members: dict[str, set[str]] = {}
        self.admin_of = {"HUBIplan", "Vorstand", "Kassierer", "Mitglieder"}
        self.changes: list[tuple[str, str, str]] = []
        # Konten, die es in der Nextcloud nicht (mehr) gibt
        self.gone: set[str] = set()
        # Administratorkonten: Gruppen-Admins bekommen für sie „nicht gefunden“ (998)
        self.admins: set[str] = set()

    def _answer(self, statuscode: int, data: dict, status: int = 200):
        payload = {"ocs": {"meta": {"statuscode": statuscode}, "data": data}}
        return safehttp.Response(status, {}, json.dumps(payload).encode())

    def __call__(self, method, url, *, headers=None, body=None, **kwargs):
        assert headers["OCS-APIRequest"] == "true"
        parts = urlsplit(url)
        path = parts.path.split("/ocs/v2.php/")[1]
        query = parse_qs(parts.query)
        if path == "cloud/user":
            return self._answer(200, {"id": "hubiplan-dienst", "subadmin": sorted(self.admin_of)})
        segments = path.split("/")
        if segments == ["cloud", "users"]:
            # Benutzerliste der Gruppen, die das Dienstkonto verwaltet (auch Administratoren)
            search = query.get("search", [""])[0].casefold()
            known = (set(self.members) | self.admins) - self.gone
            return self._answer(200, {"users": sorted(u for u in known if search in u.casefold())})
        assert segments[:2] == ["cloud", "users"] and segments[3] == "groups", path
        user = unquote(segments[2])
        if user in self.gone or user in self.admins:
            return self._answer(998, {}, 404)
        groups = self.members.setdefault(user, set())
        if method == "GET":
            return self._answer(200, {"groups": sorted(groups)})
        group = query["groupid"][0]
        if group not in self.admin_of:
            return self._answer(104, {}, 200)
        self.changes.append((method, user, group))
        if method == "POST":
            groups.add(group)
        else:
            groups.discard(group)
        return self._answer(200, {})


@pytest.fixture
def cloud(monkeypatch):
    fake = FakeGroups()
    monkeypatch.setattr(safehttp, "request", fake)
    return fake


def synced(org, **extra):
    return make_client(
        org,
        service_user="hubiplan-dienst",
        service_password=encrypt("app-passwort", purpose="nextcloud"),
        account_group="HUBIplan",
        sync_groups=True,
        sync_groups_list="Vorstand, Kassierer, Mitglieder",
        **extra,
    )


def test_wanted_nur_abgeglichene_gruppen(api, orgs, board_a, cloud):
    client, secret = synced(orgs["a"], usernames="vorstand-a@example.org = vbisher")
    login(api, client, secret, board_a)
    # Rollenname (z. B. „Vorstand“-Rolle) geht nur, soweit er in der Liste steht
    assert set(nc_groups.wanted_groups(client, board_a)) <= {
        "Vorstand",
        "Kassierer",
        "Mitglieder",
        "HUBIplan",
    }
    assert "HUBIplan" in nc_groups.wanted_groups(client, board_a)
    assert "Vorstand" in nc_groups.wanted_groups(client, board_a)


def test_rolle_endet_gruppe_faellt_weg_konto_bleibt(api, orgs, board_a, cloud):
    client, secret = synced(orgs["a"], usernames="vorstand-a@example.org = vbisher")
    login(api, client, secret, board_a)
    # Nach der Anmeldung (user_oidc) ist das Konto in seinen Gruppen, von Hand dazu „Fotos“
    cloud.members["vbisher"] = {"HUBIplan", "Vorstand", "Fotos"}
    # Wer Rollen verwaltet, bekommt die Mail
    give_role(make_user("chef@example.org"), orgs["a"], name="Vorsitz")
    first = nc_groups.sync(client)
    assert first["removed"] == 0 and first["errors"] == 0

    end_roles(board_a)
    result = nc_groups.sync(client)
    assert result["removed"] == 1
    # Kontengruppe bleibt (Dienstkonto behält das Konto in der Hand), „Fotos“ fasst HUBIplan
    # nie an
    assert cloud.members["vbisher"] == {"HUBIplan", "Fotos"}
    assert ("DELETE", "vbisher", "Vorstand") in cloud.changes
    assert any("aus „Vorstand“ entfernt" in m.body for m in mail.outbox)


def test_neue_rolle_kommt_ohne_neue_anmeldung(api, orgs, cloud):
    kassierer = make_user("kasse@example.org")
    role = give_role(kassierer, orgs["a"], [], name="1. Kassierer").role
    client, secret = synced(orgs["a"], role_groups={str(role.pk): ["Kassierer"]})
    claims = login(api, client, secret, kassierer)
    nc_user = claims["sub"]
    cloud.members[nc_user] = {"HUBIplan"}
    nc_groups.sync(client)
    assert {"HUBIplan", "Vorstand", "Kassierer"} <= cloud.members[nc_user]


def test_aus_heisst_nichts_tun(api, orgs, board_a, cloud):
    client, secret = synced(orgs["a"])
    login(api, client, secret, board_a)
    with rls_bypass():
        Client.objects.filter(pk=client.pk).update(sync_groups=False)
    client.refresh_from_db()
    end_roles(board_a)
    nc_groups.sync(client)
    assert cloud.changes == []


def test_nie_admin(api, orgs, board_a, cloud):
    client, secret = synced(orgs["a"])
    with rls_bypass():
        Client.objects.filter(pk=client.pk).update(sync_groups_list="Vorstand, admin")
    client.refresh_from_db()
    assert "admin" not in client.managed_groups()


def test_obergrenze_haelt_an(api, orgs, cloud):
    client, secret = synced(orgs["a"])
    names = []
    for i in range(5):
        user = make_user(f"vorstand{i}@example.org")
        give_role(user, orgs["a"], name=f"Rolle {i}")
        names.append((user, login(api, client, secret, user)["sub"]))
    for _user, nc_user in names:
        cloud.members[nc_user] = {"HUBIplan", "Vorstand"}
    for user, _nc_user in names[:4]:
        end_roles(user)
    result = nc_groups.sync(client)
    assert result["held"] and cloud.changes == []
    client.refresh_from_db()
    assert "4" in client.groups_error
    assert nc_groups.sync(client, confirmed=True)["removed"] == 4


def test_fehlende_adminrechte_werden_vermerkt(api, orgs, board_a, cloud):
    client, secret = synced(orgs["a"])
    nc_user = login(api, client, secret, board_a)["sub"]
    cloud.members[nc_user] = {"HUBIplan"}
    cloud.admin_of.discard("Vorstand")
    assert nc_groups.missing_admin(client) == ["Vorstand"]
    result = nc_groups.sync(client)
    assert result["errors"] == 1
    client.refresh_from_db()
    assert "Gruppen-Admin" in client.groups_error


def test_geloeschtes_konto_ist_kein_fehler_und_meldet_sich_einmal(api, orgs, board_a, cloud):
    client, secret = synced(orgs["a"], usernames="vorstand-a@example.org = vbisher")
    login(api, client, secret, board_a)
    give_role(make_user("chef@example.org"), orgs["a"], name="Vorsitz")
    cloud.gone.add("vbisher")
    mail.outbox.clear()
    result = nc_groups.sync(client)
    assert result["errors"] == 0 and result["missing"] == 1
    client.refresh_from_db()
    assert client.groups_error == ""
    # Die Mail nennt das Konto und was zu tun ist
    assert len(mail.outbox) == 1
    body = mail.outbox[0].body
    assert "vbisher (vorstand-a@example.org)" in body
    assert "Bisherige Benutzernamen" in body and "gelöscht" in body
    # Nächste Nacht: keine neue Mail
    nc_groups.sync(client)
    assert len(mail.outbox) == 1
    # Der Bericht auf der Seite zeigt es als Hinweis
    report = api(board_a).get(f"/api/orgs/{orgs['a'].pk}/nextcloud/{client.pk}/groups/").json()
    row = next(a for a in report["accounts"] if a["nc_user"] == "vbisher")
    assert row["missing"] and "gelöscht" in row["error"]
    # Gibt es das Konto wieder, verschwindet der Vermerk
    cloud.gone.clear()
    cloud.members["vbisher"] = {"HUBIplan"}
    nc_groups.sync(client)
    with rls_bypass():
        assert Account.objects.get(client=client).error == ""


def test_administratorkonto_wird_erkannt_und_ausgelassen(api, orgs, board_a, cloud):
    client, secret = synced(orgs["a"], usernames="vorstand-a@example.org = vbisher")
    login(api, client, secret, board_a)
    give_role(make_user("chef@example.org"), orgs["a"], name="Vorsitz")
    # Das Konto gibt es, es ist aber Administrator: die Nextcloud sagt „nicht gefunden“
    cloud.admins.add("vbisher")
    mail.outbox.clear()
    result = nc_groups.sync(client)
    assert result["errors"] == 0 and result["missing"] == 1 and cloud.changes == []
    client.refresh_from_db()
    assert client.groups_error == ""
    assert len(mail.outbox) == 1
    assert "vbisher (vorstand-a@example.org): Das Konto ist Administrator" in mail.outbox[0].body
    nc_groups.sync(client)
    assert len(mail.outbox) == 1
    report = api(board_a).get(f"/api/orgs/{orgs['a'].pk}/nextcloud/{client.pk}/groups/").json()
    row = next(a for a in report["accounts"] if a["nc_user"] == "vbisher")
    assert row["missing"] and "Administrator" in row["error"]


def test_fehler_nennt_das_konto(api, orgs, board_a, cloud):
    client, secret = synced(orgs["a"], usernames="vorstand-a@example.org = vbisher")
    login(api, client, secret, board_a)
    cloud.members["vbisher"] = {"HUBIplan"}
    cloud.admin_of.discard("Vorstand")
    nc_groups.sync(client)
    client.refresh_from_db()
    assert client.groups_error.startswith("1 Gruppenänderung ging nicht.")
    assert "vbisher (vorstand-a@example.org)" in client.groups_error


def test_bericht_und_einschalten_ueber_die_seite(api, orgs, board_a, cloud):
    client, secret = make_client(orgs["a"])
    url = f"/api/orgs/{orgs['a'].pk}/nextcloud/{client.pk}/"
    c = api(board_a)
    # Ohne Dienstkonto und Kontengruppe geht es nicht
    resp = c.patch(url, {"sync_groups": True}, content_type=JSON)
    assert resp.status_code == 400
    resp = c.patch(
        url,
        {
            "service_user": "hubiplan-dienst",
            "service_password": "geheim-123",
            "account_group": "HUBIplan",
            "sync_groups_list": " Vorstand ,Kassierer, Vorstand",
            "sync_groups": True,
        },
        content_type=JSON,
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["sync_groups_list"] == "Vorstand, Kassierer"
    # Die Administratorgruppe lässt sich nicht eintragen
    resp = c.patch(url, {"sync_groups_list": "Vorstand, admin"}, content_type=JSON)
    assert resp.status_code == 400

    client.refresh_from_db()
    nc_user = login(api, client, secret, board_a)["sub"]
    cloud.members[nc_user] = {"HUBIplan", "Kassierer"}
    report = c.get(url + "groups/").json()
    assert report["managed"] == ["Vorstand", "Kassierer", "HUBIplan"]
    row = report["accounts"][0]
    assert row["add"] == ["Vorstand"] and row["remove"] == ["Kassierer"]
    # Der Bericht ändert nichts
    assert cloud.changes == []
    resp = c.post(url + "groups/", {"confirm": True}, content_type=JSON)
    assert resp.status_code == 200, resp.content
    assert resp.json()["result"]["added"] == 1
    assert cloud.members[nc_user] == {"HUBIplan", "Vorstand"}


def test_einschalten_braucht_bestaetigung(api, orgs, board_a, settings):
    client, _ = synced(orgs["a"])
    with rls_bypass():
        Client.objects.filter(pk=client.pk).update(sync_groups=False)
    settings.MFA_STEP_UP = True
    url = f"/api/orgs/{orgs['a'].pk}/nextcloud/{client.pk}/"
    resp = api(board_a).patch(url, {"sync_groups": True}, content_type=JSON)
    assert resp.status_code == 403 and resp.json().get("step_up")
    resp = api(board_a).patch(url, {"sync_groups_list": "Vorstand"}, content_type=JSON)
    assert resp.status_code == 403
    # Unveränderte Liste (anders geschrieben) braucht das nicht
    resp = api(board_a).patch(
        url, {"sync_groups_list": "Vorstand,Kassierer ,Mitglieder"}, content_type=JSON
    )
    assert resp.status_code == 200, resp.content


def test_aenderung_stoesst_gruppenabgleich_an(orgs, board_a, django_capture_on_commit_callbacks):
    from oidc import signals

    client, _ = synced(orgs["a"])
    with rls_bypass():
        from oidc.models import Account

        Account.objects.create(
            organization=orgs["a"],
            client=client,
            user=board_a,
            nc_user="vbisher",
            last_login_at="2026-11-01T10:00:00Z",
        )
    queued = []
    import oidc.tasks as tasks

    original = tasks.sync_user.delay
    tasks.sync_user.delay = queued.append
    try:
        with django_capture_on_commit_callbacks(execute=True):
            signals._queue({board_a.pk})
    finally:
        tasks.sync_user.delay = original
    assert queued == [board_a.pk]
