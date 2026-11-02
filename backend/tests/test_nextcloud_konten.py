"""Nextcloud-Konten automatisch deaktivieren, wenn der Zugang in HUBIplan endet (oidc)."""

from __future__ import annotations

import datetime
import json

import pytest
from django.core import mail

from access.models import RoleAssignment
from accounts.mfa import encrypt
from core import safehttp
from core.tenancy import rls_bypass, tenant_context
from oidc import nc_accounts
from oidc.models import Account, Client

from .factories import give_role, make_user
from .test_nextcloud_anmeldung import _key, code_of, make_client, redeem, start, verify_jwt  # noqa: F401

JSON = "application/json"
YESTERDAY = datetime.date.today() - datetime.timedelta(days=1)


class FakeNextcloud:
    """Nachgebaute OCS-Schnittstelle: merkt sich Aufrufe, Antwort wie die Nextcloud."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.status = 200
        self.statuscode = 200

    def __call__(self, method, url, *, headers=None, body=None, **kwargs):
        assert headers["OCS-APIRequest"] == "true"
        assert headers["Authorization"].startswith("Basic ")
        self.calls.append((method, url.split("/ocs/v2.php/")[1].split("?")[0]))
        data = {"id": "hubiplan-dienst", "display-name": "HUBIplan-Dienst"}
        payload = {"ocs": {"meta": {"statuscode": self.statuscode}, "data": data}}
        return safehttp.Response(self.status, {}, json.dumps(payload).encode())


@pytest.fixture
def cloud(monkeypatch):
    fake = FakeNextcloud()
    monkeypatch.setattr(safehttp, "request", fake)
    return fake


def managed(org, **extra):
    return make_client(
        org,
        manage_accounts=True,
        service_user="hubiplan-dienst",
        service_password=encrypt("app-passwort"),
        account_group="HUBIplan",
        **extra,
    )


def login(api, client, secret, user) -> dict:
    return verify_jwt(redeem(client, secret, code_of(start(api(user), client))).json()["id_token"])


def end_roles(user):
    with rls_bypass():
        RoleAssignment.all_objects.filter(user=user).update(valid_until=YESTERDAY)


def test_anmeldung_merkt_konto_und_gruppe(api, orgs, board_a):
    client, secret = managed(orgs["a"], usernames="vorstand-a@example.org = vbisher")
    claims = login(api, client, secret, board_a)
    assert "HUBIplan" in claims["groups"]
    with rls_bypass():
        account = Account.objects.get(client=client)
    assert account.user == board_a and account.nc_user == "vbisher"
    assert account.organization_id == orgs["a"].pk


def test_ohne_bisherigen_namen_gilt_sub(api, orgs, board_a):
    client, secret = managed(orgs["a"])
    claims = login(api, client, secret, board_a)
    with rls_bypass():
        assert Account.objects.get(client=client).nc_user == claims["sub"]


def test_rolle_endet_konto_wird_deaktiviert_und_wieder_aktiviert(api, orgs, board_a, cloud):
    client, secret = managed(orgs["a"], usernames="vorstand-a@example.org = vbisher")
    login(api, client, secret, board_a)
    # Noch berechtigt: nichts zu tun
    assert nc_accounts.sync(client) == {"disabled": 0, "enabled": 0, "errors": 0, "held": False}
    assert cloud.calls == []

    end_roles(board_a)
    result = nc_accounts.sync(client)
    assert result["disabled"] == 1
    assert cloud.calls == [("PUT", "cloud/users/vbisher/disable")]
    with rls_bypass():
        account = Account.objects.get(client=client)
    assert account.disabled_by_hubiplan
    # Zweiter Lauf: schon deaktiviert, kein neuer Auftrag
    nc_accounts.sync(client)
    assert len(cloud.calls) == 1

    give_role(board_a, orgs["a"], name="Kassierer")
    assert nc_accounts.sync(client)["enabled"] == 1
    assert cloud.calls[-1] == ("PUT", "cloud/users/vbisher/enable")
    # Mail an die Rollenverwaltung (Kassierer hat alle Rechte der Fabrik)
    assert any("vbisher" in m.body for m in mail.outbox)


def test_nur_konten_ueber_hubiplan(api, orgs, board_a, cloud):
    client, _ = managed(orgs["a"])
    # Kein Konto angemeldet: der Abgleich fasst nichts an (auch kein admin)
    end_roles(board_a)
    nc_accounts.sync(client)
    assert cloud.calls == []


def test_aus_heisst_nichts_tun(api, orgs, board_a, cloud):
    client, secret = managed(orgs["a"])
    login(api, client, secret, board_a)
    with rls_bypass():
        Client.objects.filter(pk=client.pk).update(manage_accounts=False)
    client.refresh_from_db()
    end_roles(board_a)
    nc_accounts.sync(client)
    assert cloud.calls == []


def test_obergrenze_haelt_an(api, orgs, cloud):
    client, secret = managed(orgs["a"])
    users = []
    for i in range(5):
        user = make_user(f"vorstand{i}@example.org")
        give_role(user, orgs["a"], name=f"Rolle {i}")
        login(api, client, secret, user)
        users.append(user)
    for user in users[:4]:
        end_roles(user)
    result = nc_accounts.sync(client)
    assert result["held"] and cloud.calls == []
    client.refresh_from_db()
    assert "4" in client.sync_error
    # Von Hand bestätigt: dann doch
    assert nc_accounts.sync(client, confirmed=True)["disabled"] == 4


def test_fehler_der_nextcloud_wird_vermerkt(api, orgs, board_a, cloud):
    client, secret = managed(orgs["a"])
    login(api, client, secret, board_a)
    end_roles(board_a)
    cloud.status, cloud.statuscode = 403, 403
    assert nc_accounts.sync(client)["errors"] == 1
    with rls_bypass():
        account = Account.objects.get(client=client)
    assert not account.disabled_by_hubiplan and "Gruppen-Admin" in account.error


def test_neue_anmeldung_hebt_vermerk_auf(api, orgs, board_a, cloud):
    client, secret = managed(orgs["a"])
    login(api, client, secret, board_a)
    with rls_bypass():
        Account.objects.filter(client=client).update(disabled_by_hubiplan=True)
    login(api, client, secret, board_a)
    with rls_bypass():
        assert not Account.objects.get(client=client).disabled_by_hubiplan


def test_einstellungen_passwort_nie_in_der_antwort(api, orgs, board_a, cloud):
    client, _ = make_client(orgs["a"])
    url = f"/api/orgs/{orgs['a'].pk}/nextcloud/{client.pk}/"
    c = api(board_a)
    # Einschalten ohne Dienstkonto geht nicht
    resp = c.patch(url, {"manage_accounts": True}, content_type=JSON)
    assert resp.status_code == 400
    resp = c.patch(
        url,
        {
            "manage_accounts": True,
            "service_user": "hubiplan-dienst",
            "service_password": "geheim-123",
            "account_group": "HUBIplan",
        },
        content_type=JSON,
    )
    assert resp.status_code == 200, resp.content
    data = resp.json()
    assert "service_password" not in data and data["has_service_password"]
    assert "geheim-123" not in resp.content.decode()
    client.refresh_from_db()
    assert client.service_password.startswith("enc1:")
    # Leeres Passwort behält das gespeicherte
    resp = c.patch(url, {"service_password": ""}, content_type=JSON)
    client.refresh_from_db()
    assert resp.status_code == 200 and client.service_password.startswith("enc1:")

    resp = c.post(f"{url}check/", content_type=JSON)
    assert resp.status_code == 200 and "HUBIplan-Dienst" in resp.json()["detail"]
    assert cloud.calls == [("GET", "cloud/user")]


def test_probelauf_in_der_liste(api, orgs, board_a, cloud):
    client, secret = managed(orgs["a"])
    other = make_user("zweiter@example.org")
    give_role(other, orgs["a"], name="Schriftführer")
    login(api, client, secret, other)
    end_roles(other)
    rows = api(board_a).get(f"/api/orgs/{orgs['a'].pk}/nextcloud/{client.pk}/accounts/").json()
    assert [(r["email"], r["planned"]) for r in rows] == [("zweiter@example.org", "disable")]
    assert cloud.calls == []


def test_fremde_einheit_sieht_keine_konten(api, orgs, board_a, board_b):
    client, secret = managed(orgs["a"])
    login(api, client, secret, board_a)
    resp = api(board_b).get(f"/api/orgs/{orgs['a'].pk}/nextcloud/{client.pk}/accounts/")
    assert resp.status_code == 404
    with tenant_context(orgs["b"].pk):
        assert not Account.objects.exists()
