"""Verbindungscode an die App gebunden (Gesamtaudit 15.11., APP-01; Fachfrage FF-06 (a)).

Der Browser gab den Einmalcode über hubiplan://verbinden an „die“ App. Eigene URL-Schemata
sind nicht exklusiv: Eine fremde App mit demselben Schema konnte den Code abfangen und sich
mit dem Konto verbinden. Jetzt schickt die App beim Öffnen von /app/anmelden einen Prüfwert
(SHA-256 ihres Geheimnisses) mit; einlösen kann den Code nur, wer das Geheimnis kennt. Codes
ohne Prüfwert (QR-Code, ältere Apps) gelten im Übergang weiter. Erfundene Daten.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

import base64
import hashlib

import pytest
from django.test import Client

from devices.models import Device, PairingCode, challenge_of

from .test_app_devices import APP, member, pair  # noqa: F401
from .test_m12_events import JSON, cal  # noqa: F401

pytestmark = pytest.mark.django_db

VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"  # Beispiel aus RFC 7636, Anhang B
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def _code(api, user, challenge=None) -> str:
    body = {"challenge": challenge} if challenge is not None else {}
    resp = api(user).post(f"{APP}pairing/", body, content_type=JSON)
    assert resp.status_code == 201, resp.json()
    return resp.json()["url"].split("#code=")[1]


def _pair(code, verifier=None):
    body = {"code": code, "name": "Pixel 8", "app_version": "2"}
    if verifier is not None:
        body["verifier"] = verifier
    return Client().post(f"{APP}pair/", body, content_type=JSON)


def test_pruefwert_wie_rfc7636():
    assert challenge_of(VERIFIER) == CHALLENGE
    digest = hashlib.sha256(VERIFIER.encode()).digest()
    assert base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == CHALLENGE


def test_code_mit_pruefwert_nur_mit_passendem_geheimnis(member, api):
    user, _ = member
    code = _code(api, user, CHALLENGE)
    assert PairingCode.objects.get().challenge == CHALLENGE
    resp = _pair(code, VERIFIER)
    assert resp.status_code == 201, resp.json()
    assert Device.objects.count() == 1


@pytest.mark.parametrize("verifier", [None, "", "x" * 43, VERIFIER[:-1] + "Y"])
def test_ohne_oder_mit_falschem_geheimnis_abgelehnt_und_verbraucht(member, api, verifier):
    user, _ = member
    code = _code(api, user, CHALLENGE)
    # Die fremde App kennt das Geheimnis nicht
    assert _pair(code, verifier).status_code in (400, 404)
    assert Device.objects.count() == 0
    if verifier not in (None, ""):
        # Fehlversuch verbraucht den Code: auch die echte App muss neu anfordern
        assert PairingCode.objects.get().used_at is not None
        assert _pair(code, VERIFIER).status_code == 404


def test_geheimnis_mit_ungueltigen_zeichen_abgelehnt(member, api):
    user, _ = member
    code = _code(api, user, CHALLENGE)
    assert _pair(code, "ä" * 43).status_code == 400
    assert _pair(code, "a" * 200).status_code == 400


def test_ungueltiger_pruefwert_beim_anfordern(member, api):
    user, _ = member
    resp = api(user).post(f"{APP}pairing/", {"challenge": "kurz"}, content_type=JSON)
    assert resp.status_code == 400
    assert not PairingCode.objects.exists()


def test_qr_code_ohne_pruefwert_wie_bisher(member, api):
    """Übergang: QR-Code und ältere Apps ohne Prüfwert verbinden sich weiter; ein mitgeschicktes
    Geheimnis stört dabei nicht."""
    user, _ = member
    assert _pair(_code(api, user)).status_code == 201
    assert _pair(_code(api, user), VERIFIER).status_code == 201


def test_instanz_meldet_die_funktion():
    assert "app-pruefwert" in Client().get(f"{APP}instance/").json()["features"]
