"""Nextcloud: Verwaltungs- und Dienstkonten nie zuordnen (Gesamtaudit 15.11., AUTH-07).

Wer „Rollen verwalten“ hatte, konnte sein Konto auf den Nextcloud-Benutzer „admin“ abbilden.
Jetzt sind admin, root, administrator und das Dienstkonto gesperrt; gespeicherte Zeilen zeigt
die Ansicht, gelöscht wird nichts. Änderungen an Zuordnungen brauchen eine frische Bestätigung
und gehen als Hinweis an alle mit „Rollen verwalten“. Erfundene Daten.
"""

import pytest
from django.core import mail

from core.tenancy import rls_bypass
from oidc import nc_accounts
from oidc.models import Account, parse_usernames

from .factories import make_user
from .test_nextcloud_anmeldung import _key, make_client  # noqa: F401

pytestmark = pytest.mark.django_db
JSON = "application/json"


def _url(org, client=None):
    base = f"/api/orgs/{org.pk}/nextcloud/"
    return f"{base}{client.pk}/" if client else base


def test_gesperrte_namen():
    lines = parse_usernames(
        "a@example.org = admin\nb@example.org = bmuster\nc@example.org = svc", {"svc"}
    )
    assert [e for _m, _n, e in lines] == ["blocked", "", "blocked"]


def test_bestehende_zeile_wird_gezeigt_und_nie_zugeordnet(api, orgs, board_a):
    client, _secret = make_client(
        orgs["a"], usernames="vorstand-a@example.org = admin\nx@example.org = xmuster"
    )
    assert client.username_map() == {"x@example.org": "xmuster"}
    data = api(board_a).get(_url(orgs["a"], client)).json()
    assert data["blocked_usernames"] == ["vorstand-a@example.org = admin"]
    assert "admin" in data["usernames"]  # nichts still gelöscht


def test_speichern_mit_gesperrtem_namen_abgewiesen(api, orgs, board_a):
    client, _secret = make_client(orgs["a"], service_user="hubiplan-dienst")
    resp = api(board_a).patch(
        _url(orgs["a"], client),
        {"usernames": "vorstand-a@example.org = hubiplan-dienst"},
        content_type=JSON,
    )
    assert resp.status_code == 400
    assert "Dienstkonten" in str(resp.json())


def test_abgleich_fasst_admin_nie_an(orgs):
    client, _secret = make_client(orgs["a"], manage_accounts=True)
    user = make_user("ehemals-admin@example.org")
    with rls_bypass():
        Account.objects.create(
            organization=orgs["a"],
            client=client,
            user=user,
            nc_user="admin",
            last_login_at="2026-01-01T00:00:00Z",
        )
    assert nc_accounts.plan(client) == []


def test_aenderung_braucht_bestaetigung_und_meldet(
    api, orgs, board_a, settings, django_capture_on_commit_callbacks
):
    client, _secret = make_client(orgs["a"])
    settings.MFA_STEP_UP = True
    resp = api(board_a).patch(
        _url(orgs["a"], client), {"usernames": "x@example.org = xmuster"}, content_type=JSON
    )
    assert resp.status_code == 403 and resp.json().get("step_up")
    settings.MFA_STEP_UP = False
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        resp = api(board_a).patch(
            _url(orgs["a"], client), {"usernames": "x@example.org = xmuster"}, content_type=JSON
        )
    assert resp.status_code == 200, resp.content
    notes = [m for m in mail.outbox if m.subject == "Nextcloud-Zuordnung geändert"]
    assert [m.to for m in notes] == [[board_a.email]]
