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
from .test_nextcloud_anmeldung import (  # noqa: F401
    _key,
    code_of,
    make_client,
    redeem,
    start,
    verify_jwt,
)
from .test_rls import as_app_role

JSON = "application/json"
YESTERDAY = datetime.date.today() - datetime.timedelta(days=1)


class FakeNextcloud:
    """Nachgebaute OCS-Schnittstelle: merkt sich Aufrufe, Antwort wie die Nextcloud."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.status = 200
        self.statuscode = 200
        # Wie eine Nextcloud, die fürs Aktivieren/Deaktivieren eine Passwortbestätigung verlangt
        self.confirm = False

    def __call__(self, method, url, *, headers=None, body=None, **kwargs):
        assert headers["OCS-APIRequest"] == "true"
        assert headers["Authorization"].startswith("Basic ")
        path = url.split("/ocs/v2.php/")[1].split("?")[0]
        if path.startswith("cloud/users/hubiplan-pruefung-"):
            # Probe der Verbindungsprüfung: Benutzer gibt es nicht (oder vorher schon 403)
            code = 403 if self.confirm else 404
            payload = {"ocs": {"meta": {"statuscode": code}, "data": {}}}
            return safehttp.Response(code, {}, json.dumps(payload).encode())
        self.calls.append((method, path))
        if self.confirm and method == "PUT":
            payload = {"ocs": {"meta": {"statuscode": 403}, "data": {}}}
            return safehttp.Response(403, {}, json.dumps(payload).encode())
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
        service_password=encrypt("app-passwort", purpose="nextcloud"),
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
    assert not account.disabled_by_hubiplan
    # 403 heißt bei enable/disable: Passwortbestätigung verlangt, nicht „kein Gruppen-Admin“
    assert "Passwortbestätigung" in account.error and "Gruppen-Admin" not in account.error


def test_geloeschtes_konto_ist_kein_fehler_und_meldet_sich_einmal(api, orgs, board_a, cloud):
    client, secret = managed(orgs["a"], usernames="vorstand-a@example.org = vbisher")
    login(api, client, secret, board_a)
    give_role(make_user("chef@example.org"), orgs["a"], name="Vorsitz")
    end_roles(board_a)
    # Das Konto wurde in der Nextcloud gelöscht
    cloud.status, cloud.statuscode = 404, 404
    mail.outbox.clear()
    assert nc_accounts.sync(client)["errors"] == 0
    client.refresh_from_db()
    assert client.sync_error == ""
    # Die Mail nennt das Konto und was zu tun ist
    assert len(mail.outbox) == 1
    assert "vbisher (vorstand-a@example.org)" in mail.outbox[0].body
    assert "Bisherige Benutzernamen" in mail.outbox[0].body
    # Nächste Nacht: keine neue Mail
    nc_accounts.sync(client)
    assert len(mail.outbox) == 1


def test_fehler_nennt_das_konto(api, orgs, board_a, cloud):
    client, secret = managed(orgs["a"], usernames="vorstand-a@example.org = vbisher")
    login(api, client, secret, board_a)
    end_roles(board_a)
    cloud.status, cloud.statuscode = 403, 403
    nc_accounts.sync(client)
    client.refresh_from_db()
    assert client.sync_error.startswith("1 Konto konnte nicht geändert werden.")
    assert "vbisher (vorstand-a@example.org)" in client.sync_error


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
    # Row-Level Security: in der Rolle der Anwendung sieht Verein B das Konto nicht
    with as_app_role(), tenant_context(orgs["b"].pk):
        assert not Account.objects.exists()
    with as_app_role(), tenant_context(orgs["a"].pk):
        assert Account.objects.count() == 1


# --- Issue #733: richtige Ursache, Grund, keine tägliche Wiederholung ---


def without_mfa(user):
    """Frist für die Zwei-Faktor-Anmeldung abgelaufen: Die Rechte der Rolle ruhen."""
    from django.utils import timezone

    from accounts.models import User

    with rls_bypass():
        User.objects.filter(pk=user.pk).update(
            mfa_required_by=timezone.now() - datetime.timedelta(days=30)
        )


def test_derselbe_fehler_kommt_nicht_jede_nacht(api, orgs, board_a, cloud):
    client, secret = managed(orgs["a"], usernames="vorstand-a@example.org = vbisher")
    login(api, client, secret, board_a)
    give_role(make_user("chef@example.org"), orgs["a"], name="Vorsitz")
    end_roles(board_a)
    cloud.confirm = True
    mail.outbox.clear()
    assert nc_accounts.sync(client)["errors"] == 1
    assert len(mail.outbox) == 1
    body = mail.outbox[0].body
    assert "vbisher (vorstand-a@example.org)" in body
    assert "keine Rolle mit Zugang mehr" in body
    assert "Passwortbestätigung" in body and "allowed_no_password_confirmation_ranges" in body
    assert "Gruppen-Admin" not in body
    # Nächste Nacht: derselbe Fehler, keine neue Mail; die Seite zeigt ihn weiter
    assert nc_accounts.sync(client)["errors"] == 1
    assert len(mail.outbox) == 1
    client.refresh_from_db()
    assert "vbisher" in client.sync_error
    assert "allowed_no_password_confirmation_ranges" in client.sync_error
    # Anderer Fehler: wieder eine Mail
    cloud.confirm = False
    cloud.status, cloud.statuscode = 500, 996
    nc_accounts.sync(client)
    assert len(mail.outbox) == 2
    # Nach langer Zeit: Erinnerung
    nc_accounts.sync(client)
    assert len(mail.outbox) == 2
    with rls_bypass():
        account = Account.objects.get(client=client)
        Account.objects.filter(pk=account.pk).update(
            error_mailed_at=account.error_mailed_at
            - datetime.timedelta(days=nc_accounts.REMIND_DAYS + 1)
        )
    nc_accounts.sync(client)
    assert len(mail.outbox) == 3
    # Erfolg räumt auf
    cloud.status, cloud.statuscode = 200, 200
    assert nc_accounts.sync(client)["disabled"] == 1
    with rls_bypass():
        account = Account.objects.get(client=client)
    assert account.error == "" and account.error_mailed_at is None


def test_grund_ohne_zwei_faktor_in_mail_und_liste(api, orgs, board_a, cloud):
    client, secret = managed(orgs["a"], usernames="zweiter@example.org = zbisher")
    other = make_user("zweiter@example.org")
    give_role(other, orgs["a"], name="Schriftführer")
    login(api, client, secret, other)
    # Rolle bleibt, aber die Frist für die Zwei-Faktor-Anmeldung ist abgelaufen
    without_mfa(other)
    url = f"/api/orgs/{orgs['a'].pk}/nextcloud/{client.pk}/accounts/"
    rows = api(board_a).get(url).json()
    assert [(r["planned"], r["reason"]) for r in rows] == [
        ("disable", "keine Zwei-Faktor-Anmeldung, Rollenrechte ruhen")
    ]
    mail.outbox.clear()
    assert nc_accounts.sync(client)["disabled"] == 1
    # Die Rollenverwaltung bekommt eine Mail (auch „zweiter“: die Rolle besteht ja weiter)
    to_managers = [m for m in mail.outbox if m.to != ["zweiter@example.org"]]
    assert any(
        "zbisher (zweiter@example.org): deaktiviert (keine Zwei-Faktor-Anmeldung" in m.body
        for m in to_managers
    )
    # Die Person selbst erfährt, warum und wie es wieder geht
    own = [m for m in mail.outbox if m.to == ["zweiter@example.org"]]
    assert len(own) == 1 and "Zwei-Faktor-Anmeldung einrichten" in own[0].body
    # Danach steht der Grund weiter in der Liste
    rows = api(board_a).get(url).json()
    assert rows[0]["disabled_by_hubiplan"] and "Zwei-Faktor" in rows[0]["reason"]


def test_grund_keine_rolle(api, orgs, board_a, cloud):
    client, secret = managed(orgs["a"])
    other = make_user("zweiter@example.org")
    give_role(other, orgs["a"], name="Schriftführer")
    login(api, client, secret, other)
    end_roles(other)
    rows = api(board_a).get(f"/api/orgs/{orgs['a'].pk}/nextcloud/{client.pk}/accounts/").json()
    assert rows[0]["reason"] == "keine Rolle mit Zugang mehr"
    mail.outbox.clear()
    nc_accounts.sync(client)
    # Keine Mail an die Person selbst (nur bei fehlender Zwei-Faktor-Anmeldung)
    assert not [m for m in mail.outbox if m.to == ["zweiter@example.org"]]


def test_verbindungspruefung_erkennt_passwortbestaetigung(api, orgs, board_a, cloud):
    client, _ = managed(orgs["a"])
    url = f"/api/orgs/{orgs['a'].pk}/nextcloud/{client.pk}/check/"
    c = api(board_a)
    resp = c.post(url, content_type=JSON)
    assert resp.status_code == 200 and resp.json()["ok"]
    cloud.confirm = True
    resp = c.post(url, content_type=JSON)
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "HUBIplan-Dienst" in detail and "allowed_no_password_confirmation_ranges" in detail
    # Die Probe fasst kein echtes Konto an
    assert all(call == ("GET", "cloud/user") for call in cloud.calls)
    # Ohne „Konten automatisch deaktivieren“ spielt es keine Rolle
    with rls_bypass():
        Client.objects.filter(pk=client.pk).update(manage_accounts=False)
    assert c.post(url, content_type=JSON).status_code == 200
