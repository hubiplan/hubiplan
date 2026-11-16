"""Eingaben mit „enc1:“ gelten nie als gespeichertes Chiffrat (Gesamtaudit 15.11., OPS-01/OPS-02).

Vorher kam ein Wert, der mit „enc1:“ begann, unverändert in die Datenbank. Mit einem Chiffrat aus
einem Datenbank-Dump ließ sich so (1) ein Feld eines fremden Vereins über ein gewöhnliches Konto
entschlüsselt lesen und (2) ein TOTP-Geheimnis über „Nextcloud-Verbindung prüfen“ an einen
fremden Server schicken.
"""

import base64
import json

import pytest
from allauth.mfa.models import Authenticator
from django.db import connection

from accounts.mfa import decrypt, encrypt, ensure_encrypted
from core import safehttp
from core.tenancy import rls_bypass

pytestmark = pytest.mark.django_db

JSON = "application/json"
GEHEIM = "Kassenbericht: Fehlbetrag 1.234,56 EUR (erfunden)"
TOTP_SECRET = "JBSWY3DPEHPK3PXP"  # erfundenes Beispielgeheimnis


def _url(org, pk=None):
    return f"/api/orgs/{org.pk}/todos/" + (f"{pk}/" if pk else "")


def test_fremdes_feld_chiffrat_bleibt_unlesbar(api, board_a, board_b, orgs):
    created = api(board_a).post(
        _url(orgs["a"]), {"title": "Intern", "description": GEHEIM}, content_type=JSON
    )
    assert created.status_code == 201, created.content
    with connection.cursor() as cursor:
        cursor.execute("SELECT description FROM todos_todo WHERE id = %s", [created.json()["id"]])
        (chiffrat,) = cursor.fetchone()
    assert chiffrat.startswith("enc1:")

    own = api(board_b).post(
        _url(orgs["b"]), {"title": "Harmlos", "description": chiffrat}, content_type=JSON
    )
    assert own.status_code == 201, own.content
    with connection.cursor() as cursor:
        cursor.execute("SELECT description FROM todos_todo WHERE id = %s", [own.json()["id"]])
        (gespeichert,) = cursor.fetchone()
    # Neu verschlüsselt (als Klartext), nicht übernommen
    assert gespeichert != chiffrat and gespeichert.startswith("enc1:")
    gelesen = api(board_b).get(_url(orgs["b"], own.json()["id"]))
    assert gelesen.status_code == 200, gelesen.content
    assert gelesen.json()["description"] == chiffrat
    assert GEHEIM not in json.dumps(gelesen.json())


def test_mfa_encrypt_verschluesselt_auch_chiffrat_eingaben():
    chiffrat = encrypt(TOTP_SECRET)
    doppelt = encrypt(chiffrat)
    assert doppelt != chiffrat
    assert decrypt(doppelt) == chiffrat
    # Bestandsläufe lassen Verschlüsseltes unverändert
    assert ensure_encrypted(chiffrat) == chiffrat
    assert decrypt(ensure_encrypted(TOTP_SECRET)) == TOTP_SECRET


def test_totp_geheimnis_fliesst_nicht_an_fremde_nextcloud(api, orgs, board_a, board_b, monkeypatch):
    with rls_bypass():
        auth = Authenticator.objects.create(
            user=board_a, type=Authenticator.Type.TOTP, data={"secret": encrypt(TOTP_SECRET)}
        )
    with connection.cursor() as cursor:
        cursor.execute("SELECT data FROM mfa_authenticator WHERE id = %s", [auth.pk])
        (raw,) = cursor.fetchone()
    chiffrat = (raw if isinstance(raw, dict) else json.loads(raw))["secret"]

    base = f"/api/orgs/{orgs['b'].pk}/nextcloud/"
    created = api(board_b).post(
        base, {"name": "Eigene Cloud", "base_url": "https://angreifer.example.org"}, JSON
    )
    assert created.status_code == 201, created.content
    url = f"{base}{created.json()['id']}/"
    patched = api(board_b).patch(
        url, {"service_user": "dienst", "service_password": chiffrat}, content_type=JSON
    )
    assert patched.status_code == 200, patched.content

    gesehen = {}

    def fremder_server(method, target, *, headers=None, body=None, **kwargs):
        gesehen["auth"] = headers["Authorization"]
        payload = {"ocs": {"meta": {"statuscode": 200}, "data": {"id": "dienst"}}}
        return safehttp.Response(200, {}, json.dumps(payload).encode())

    monkeypatch.setattr(safehttp, "request", fremder_server)
    api(board_b).post(f"{url}check/")
    _, _, passwort = base64.b64decode(gesehen["auth"].split(" ", 1)[1]).decode().partition(":")
    # Gesendet wird die Eingabe selbst, nicht das entschlüsselte fremde Geheimnis
    assert passwort == chiffrat
    assert passwort != TOTP_SECRET
