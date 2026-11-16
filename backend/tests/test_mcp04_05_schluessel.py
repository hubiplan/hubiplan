"""KI-Schnittstelle: Kopien von Schlüsseln und Codes erkennen (Gesamtaudit 15.11.).

MCP-04: Nur der unmittelbare Vorgänger eines Erneuerungsschlüssels war bekannt; ein Schlüssel,
der zwei Erneuerungen alt war, scheiterte still, und ein Diebstahl blieb unentdeckt.
MCP-05: Ein zweites Einlösen desselben Codes lieferte nur „invalid_grant“; die mit dem Code
ausgestellten Schlüssel liefen weiter. Erfundene Daten.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

from __future__ import annotations

import datetime

import pytest
from django.test import Client as HttpClient
from django.utils import timezone

from audit.models import AuditEntry
from mcpserver import tasks
from mcpserver.models import McpGrant, hash_token

from .test_mcp_verein import (  # noqa: F401
    club,
    code_of,
    connect,
    consent,
    editor,
    redeem,
    register,
    rpc,
    site,
    with_mfa,
)

pytestmark = pytest.mark.django_db(transaction=True)
TOKEN = "/api/mcp/oauth/token"


def _renew(client_id, refresh):
    return HttpClient().post(
        TOKEN, {"grant_type": "refresh_token", "client_id": client_id, "refresh_token": refresh}
    )


def test_aelterer_erneuerungsschluessel_beendet_die_verbindung(club, site, editor):
    first = connect(editor, club)
    client_id = first["client_id"]
    second = _renew(client_id, first["refresh_token"]).json()
    third = _renew(client_id, second["refresh_token"]).json()
    assert rpc(third["access_token"], "ping").status_code == 200
    grant = McpGrant.objects.get(user=editor)
    # Nur Prüfsummen, keine Schlüssel
    assert hash_token(first["refresh_token"]) in grant.retired_refresh_hashes
    assert first["refresh_token"] not in str(grant.retired_refresh_hashes)
    # Vorher: still „unbekannt“, die Verbindung lief weiter
    assert _renew(client_id, first["refresh_token"]).status_code == 400
    assert rpc(third["access_token"], "ping").status_code == 401
    grant.refresh_from_db()
    assert grant.revoked_reason == "wiederverwendet"
    entries = AuditEntry.objects.filter(organization=club, object_id=str(grant.pk))
    assert any("KI-Assistent beendet" in str(e.changes) for e in entries)


def test_doppelt_eingeloester_code_widerruft_die_schluessel(club, site, editor):
    client_id = register()["client_id"]
    code = code_of(consent(with_mfa(editor), client_id, club.pk))
    first = redeem(client_id, code)
    assert first.status_code == 200
    token = first.json()["access_token"]
    assert rpc(token, "ping").status_code == 200
    # Jemand hat den Code abgefangen und probiert ihn auch
    assert redeem(client_id, code).status_code == 400
    assert rpc(token, "ping").status_code == 401
    grant = McpGrant.objects.get(user=editor)
    assert grant.revoked_reason == "code_doppelt"


def test_unbekannter_code_widerruft_nichts(club, site, editor):
    data = connect(editor, club)
    assert redeem(data["client_id"], "gibt-es-nicht").status_code == 400
    assert rpc(data["access_token"], "ping").status_code == 200


def test_aufraeumen_nur_bei_beendeten_verbindungen(club, site, editor):
    running = connect(editor, club)
    _renew(running["client_id"], running["refresh_token"])
    ended = connect(editor, club)
    _renew(ended["client_id"], ended["refresh_token"])
    grants = McpGrant.objects.filter(user=editor).order_by("pk")
    keep, gone = grants[0], grants[1]
    gone.revoke("test")
    old = McpGrant.objects.create(
        user=editor,
        organization=club,
        client=keep.client,
        scopes=keep.scopes,
        auth_version=keep.auth_version,
        expires_at=timezone.now() - datetime.timedelta(days=1),
        last_used_at=timezone.now() - datetime.timedelta(days=20),
        access_hash="a" * 64,
        access_expires_at=timezone.now() - datetime.timedelta(days=1),
        refresh_hash="b" * 64,
        retired_refresh_hashes=["c" * 64],
    )
    assert tasks.purge_retired_refresh() == 2
    keep.refresh_from_db()
    gone.refresh_from_db()
    old.refresh_from_db()
    assert keep.retired_refresh_hashes and not gone.retired_refresh_hashes
    assert old.retired_refresh_hashes == []
