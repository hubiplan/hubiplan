"""Hochladelink endet mit der KI-Verbindung und dem Recht (Gesamtaudit 15.11., MCP-06).

Der öffentliche Link prüfte nur Ablauf, Anzahl, Einheit, Modul „Webseite“ und Konto, nicht die
KI-Verbindung, das Modul „KI-Assistenten“ und das aktuelle Recht „Inhalte bearbeiten“. Nach dem
Trennen oder einem Rechteentzug konnten bis zu 30 Minuten weiter Bilder im Namen der Person in
die Bilderverwaltung gelangen. Erfundene Daten.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

from __future__ import annotations

import pytest
from django.test import Client as HttpClient

from mcpserver.models import McpGrant
from website.models import ImageUploadLink

from .test_mcp_verein import call, club, connect, editor, site  # noqa: F401
from .test_mcp_webseite_w2 import private_root  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def _link(editor, club):
    token = connect(editor, club)["access_token"]
    text, failed = call(token, "bild_hochladen_vorbereiten")
    assert not failed, text
    url = next(w for w in text.split() if "/bilder-hochladen/" in w)
    public = f"/api/public/website-images/{url.rsplit('/', 1)[1]}/"
    assert HttpClient().get(public).status_code == 200
    return public, McpGrant.objects.get(user=editor, revoked_at=None)


def test_link_kennt_seine_verbindung(club, site, editor):
    _public, grant = _link(editor, club)
    assert ImageUploadLink.objects.get(website=site).grant_id == grant.pk


def test_trennen_beendet_den_link(club, site, editor):
    public, grant = _link(editor, club)
    grant.revoke("getrennt")
    assert HttpClient().get(public).status_code == 404
    assert ImageUploadLink.objects.get(website=site).revoked_at is not None


def test_rechteentzug_beendet_den_link(club, site, editor):
    public, _grant = _link(editor, club)
    role = editor.role_assignments.get().role
    role.permissions = [p for p in role.permissions if p != "website.content"]
    role.save()
    assert HttpClient().get(public).status_code == 404


def test_modul_aus_beendet_den_link(club, site, editor):
    public, _grant = _link(editor, club)
    club.enabled_modules = [m for m in club.enabled_modules if m != "mcp"]
    club.save()
    assert HttpClient().get(public).status_code == 404


def test_link_aus_der_oberflaeche_ohne_verbindung_wie_bisher(club, site, editor):
    link, secret = ImageUploadLink.create(site, editor, "")
    assert link.grant_id is None
    assert HttpClient().get(f"/api/public/website-images/{secret}/").status_code == 200
