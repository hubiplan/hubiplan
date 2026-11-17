# ruff: noqa: F811  (Fixtures aus test_mcp_briefbogen und test_mcp_verein)
"""Vorschläge eines KI-Assistenten für die Texte des Briefbogens (Gesamtaudit 15.11., MCP-01,
Fachfrage FF-12 a): übernehmen nur mit frischer Bestätigung, verwerfen, Ablauf nach 30 Tagen,
Ende mit der Verbindung. Erfundene Daten."""

import datetime

import pytest
from django.utils import timezone

from core.tenancy import rls_bypass
from letterhead import data as service
from letterhead.models import Letterhead, LetterheadProposal
from mcpserver.models import McpGrant

from .test_mcp_briefbogen import ALL, LETTERHEAD, secretary  # noqa: F401
from .test_mcp_verein import call, club, connect, site  # noqa: F401

pytestmark = pytest.mark.django_db
JSON = "application/json"


def _vorschlag(club, secretary):
    token = connect(secretary, club, scope=ALL, haken=[LETTERHEAD])["access_token"]
    text, failed = call(token, "briefbogen_aendern", zusatzzeile="Gegründet 1920 in Musterstadt")
    assert not failed, text
    return LetterheadProposal.objects.get(organization=club)


def test_uebernehmen_braucht_bestaetigung(api, club, site, secretary, settings):
    proposal = _vorschlag(club, secretary)
    c = api(secretary)
    state = c.get(f"/api/orgs/{club.pk}/letterhead/").json()
    assert [p["texts"] for p in state["proposals"]] == [
        {"tagline": "Gegründet 1920 in Musterstadt"}
    ]
    settings.MFA_STEP_UP = True
    resp = c.post(f"/api/orgs/{club.pk}/letterhead/proposals/{proposal.pk}/")
    assert resp.status_code == 403 and resp.json().get("step_up")
    assert service.ensure(club).tagline != "Gegründet 1920 in Musterstadt"
    settings.MFA_STEP_UP = False
    resp = c.post(f"/api/orgs/{club.pk}/letterhead/proposals/{proposal.pk}/")
    assert resp.status_code == 200, resp.content
    assert Letterhead.objects.get(organization=club).tagline == "Gegründet 1920 in Musterstadt"
    assert resp.json()["proposals"] == []


def test_verwerfen(api, club, site, secretary):
    proposal = _vorschlag(club, secretary)
    resp = api(secretary).delete(f"/api/orgs/{club.pk}/letterhead/proposals/{proposal.pk}/")
    assert resp.status_code == 204
    assert not LetterheadProposal.objects.filter(pk=proposal.pk).exists()


def test_ablauf_und_ende_der_verbindung(api, club, site, secretary):
    proposal = _vorschlag(club, secretary)
    LetterheadProposal.objects.filter(pk=proposal.pk).update(
        expires_at=timezone.now() - datetime.timedelta(minutes=1)
    )
    assert api(secretary).get(f"/api/orgs/{club.pk}/letterhead/").json()["proposals"] == []
    assert not LetterheadProposal.objects.filter(pk=proposal.pk).exists()
    zweiter = _vorschlag(club, secretary)
    with rls_bypass():
        McpGrant.objects.filter(pk=zweiter.grant_id).delete()
    assert not LetterheadProposal.objects.filter(pk=zweiter.pk).exists()
