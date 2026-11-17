"""Auskunft (Art. 15): Daten am Anmeldekonto stehen in konto.json (Gesamtaudit 15.11., PF-02/PF-20).

Vorher enthielt die Auskunft vom Konto nur Anmelde-Mail, letzte Anmeldung und Geräte; Passkeys,
E-Mail-Adressen, Nextcloud- und KI-Freigaben, Anmeldungen über andere Instanzen, gespeicherte
Unterschrift und eigene Aufgaben fehlten. Erfundene Daten.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

import datetime
import io
import json
import zipfile

import pytest
from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from django.utils import timezone

from accounts.models import StoredSignature
from core.tenancy import tenant_context
from devices.models import Device
from mcpserver.models import McpClient, McpGrant
from members.models import Membership
from portal.models import PortalAccess
from todos.models import Todo

from .factories import make_user
from .test_m3_workflows import member, types, url  # noqa: F401

# Anfragen wie im Betrieb unter dem Zeilenschutz (Gesamtaudit 15.11., AZ-04)
pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("anfragen_unter_app_rolle")]


def _konto(c, orgs, member) -> tuple[list, bytes]:
    resp = c.get(url(orgs, member, "auskunft/"))
    assert resp.status_code == 200, resp.content[:300]
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    everything = b"".join(zf.read(n) for n in zf.namelist())
    return json.loads(zf.read("konto.json")), everything


def test_konto_in_der_auskunft(api, orgs, member, board_a):
    user = make_user("erika.konto@example.org", first_name="Erika", last_name="Muster")
    membership = Membership.objects.get(pk=member["id"])
    PortalAccess.objects.create(organization=orgs["a"], membership=membership, user=user)
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    Authenticator.objects.create(
        user=user,
        type=Authenticator.Type.WEBAUTHN,
        data={"name": "Mein Schlüssel", "credential": {"geheim": "nicht-ausgeben"}},
    )
    StoredSignature.objects.create(user=user, strokes=[[[0, 0], [1, 1]]])
    Device.objects.create(
        user=user,
        name="Telefon",
        token_hash="a" * 64,
        push_kind=Device.Push.UNIFIEDPUSH,
        push_endpoint="https://push.example.org/geheimer-pfad-123",
        push_auth="geheimes-auth",
    )
    client = McpClient.objects.create(name="Erfundener Assistent", redirect_uris=[])
    now = timezone.now()
    McpGrant.objects.create(
        user=user,
        organization=orgs["a"],
        client=client,
        scopes=["webseite.lesen"],
        access_hash="b" * 64,
        access_expires_at=now + datetime.timedelta(hours=1),
        refresh_hash="c" * 64,
        expires_at=now + datetime.timedelta(days=30),
    )
    # Fremder Verein: Freigabe dort gehört nicht in die Auskunft von Verein A
    McpGrant.objects.create(
        user=user,
        organization=orgs["b"],
        client=client,
        scopes=["webseite.lesen"],
        access_hash="d" * 64,
        access_expires_at=now + datetime.timedelta(hours=1),
        refresh_hash="e" * 64,
        expires_at=now + datetime.timedelta(days=30),
    )
    with tenant_context(orgs["a"].pk):
        Todo.objects.create(organization=orgs["a"], title="Private Notiz", owner=user)
        Todo.objects.create(
            organization=orgs["a"], title="Geteilte Aufgabe", owner=user, shared=True
        )

    [konto], everything = _konto(api(board_a), orgs, member)
    assert konto["anmelde_email"] == "erika.konto@example.org"
    assert konto["email_adressen"] == [
        {"email": "erika.konto@example.org", "bestätigt": True, "haupt": True}
    ]
    assert [(a["art"], a["name"]) for a in konto["zwei_faktor"]] == [("webauthn", "Mein Schlüssel")]
    assert konto["gespeicherte_unterschrift"]["vorhanden"] is True
    [geraet] = konto["geräte"]
    assert geraet["name"] == "Telefon" and geraet["benachrichtigungsdienst"] == "push.example.org"
    [assistent] = konto["ki_assistenten"]
    assert assistent["assistent"] == "Erfundener Assistent"
    eigene = konto["aufgaben"]["eigene"]
    assert len(eigene) == 2
    assert [t.get("titel") for t in eigene] == [None, "Geteilte Aufgabe"]

    # Nie Schlüssel, Prüfsummen, Push-Adresse oder Inhalte persönlicher Aufgaben
    for secret in (
        b"nicht-ausgeben",
        b"geheimer-pfad-123",
        b"geheimes-auth",
        b"a" * 64,
        b"b" * 64,
        b"Private Notiz",
    ):
        assert secret not in everything


def test_konto_ohne_zugang_ist_leer(api, orgs, member, board_a):
    konto, _ = _konto(api(board_a), orgs, member)
    assert konto == []
