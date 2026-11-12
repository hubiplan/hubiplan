"""KI-Assistenten mit Anmeldung (Stufe 1a) und Webseite als Entwurf (W1), docs/mcp.md.

Alle Daten erfunden.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from allauth.account.internal.flows.login import AUTHENTICATION_METHODS_SESSION_KEY
from allauth.mfa.models import Authenticator
from django.core import mail
from django.test import Client as HttpClient
from django.utils import timezone

from audit.models import AuditEntry
from core.tenancy import rls_bypass
from mcpserver.models import McpClient, McpGrant
from mcpserver.oauth import redirect_kind
from website.content_models import WebsiteText
from website.models import Website

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db(transaction=True)

JSON = "application/json"
REDIRECT = "https://assistent.example.org/callback"
VERIFIER = "pruefwert-" * 6
TEXT = {
    "key": "c:t1",
    "kind": "text",
    "on": True,
    "data": {"title": "Über uns", "text": "Seit 1900."},
}


def challenge(verifier: str = VERIFIER) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


@pytest.fixture
def club(orgs):
    org = orgs["a"]
    org.enabled_modules = ["members", "events", "website", "mcp"]
    org.save()
    return org


@pytest.fixture
def site(club):
    site = Website.objects.create(
        organization=club,
        public_key="mcp-a",
        state="public",
        privacy_mode="link",
        privacy_url="https://example.org/datenschutz",
    )
    site.home_sections = [{"key": "greeting", "on": True}, TEXT]
    site.save()
    return site


def with_mfa(user, client: HttpClient | None = None) -> HttpClient:
    Authenticator.objects.get_or_create(
        user=user, type=Authenticator.Type.TOTP, defaults={"data": {}}
    )
    c = client or HttpClient()
    c.force_login(user)
    session = c.session
    session[AUTHENTICATION_METHODS_SESSION_KEY] = [
        {"method": "password", "at": time.time()},
        {"method": "mfa", "at": time.time(), "type": "totp"},
    ]
    session.save()
    return c


@pytest.fixture
def editor(club):
    user = make_user("ki-redaktion@example.org", first_name="Erika", last_name="Muster")
    give_role(user, club, permissions=["website.content", "mcp.connect"], name="Redaktion")
    return user


def register(**extra) -> dict:
    body = {"client_name": "Testassistent", "redirect_uris": [REDIRECT], **extra}
    resp = HttpClient().post("/api/mcp/oauth/register", json.dumps(body), content_type=JSON)
    assert resp.status_code == 201, resp.content
    return resp.json()


def params(client_id: str, **extra) -> dict:
    data = {
        "client_id": client_id,
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "code_challenge": challenge(),
        "code_challenge_method": "S256",
        "state": "zustand-1",
        "scope": "webseite.lesen webseite.entwurf",
        **extra,
    }
    return {k: v for k, v in data.items() if v is not None}


def consent(c, client_id, org_id, **extra):
    return c.post(
        "/api/mcp/oauth/authorize/",
        {"params": params(client_id, **extra), "organization": org_id},
        content_type=JSON,
    )


def code_of(resp) -> str:
    assert resp.status_code == 200, resp.content
    url = resp.json()["redirect"]
    assert url.startswith(REDIRECT + "?")
    query = parse_qs(urlsplit(url).query)
    assert query["state"] == ["zustand-1"]
    assert query["iss"][0].endswith("/api/mcp/oauth")
    return query["code"][0]


def redeem(client_id: str, code: str, **extra):
    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        "redirect_uri": REDIRECT,
        "code_verifier": VERIFIER,
        **extra,
    }
    return HttpClient(enforce_csrf_checks=True).post("/api/mcp/oauth/token", data)


def connect(user, club, scope="webseite.lesen webseite.entwurf") -> dict:
    client_id = register()["client_id"]
    c = with_mfa(user)
    resp = redeem(client_id, code_of(consent(c, client_id, club.pk, scope=scope)))
    assert resp.status_code == 200, resp.content
    return {"client_id": client_id, **resp.json()}


def rpc(token, method, params=None, msg_id=1):
    body = {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}}
    headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
    return HttpClient().post("/api/mcp/verein/", json.dumps(body), content_type=JSON, **headers)


def call(token, name, **args):
    resp = rpc(token, "tools/call", {"name": name, "arguments": args})
    assert resp.status_code == 200, resp.content
    result = resp.json()["result"]
    return result["content"][0]["text"], result["isError"]


# --- Beschreibungen ---


def test_adresse_ohne_schraegstrich_antwortet_ohne_weiterleitung(db):
    # claude.ai prüft die Connector-Adresse ohne Schrägstrich und bricht bei 301 ab
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    resp = HttpClient().post("/api/mcp/verein", body, content_type=JSON)
    assert resp.status_code == 401
    assert resp["WWW-Authenticate"].startswith("Bearer resource_metadata=")


def test_ohne_schluessel_401_mit_hinweis_auf_anmeldung(db):
    resp = rpc(None, "initialize")
    assert resp.status_code == 401
    header = resp["WWW-Authenticate"]
    assert header.startswith("Bearer resource_metadata=")
    url = header.split('"')[1]
    path = urlsplit(url).path
    assert path == "/.well-known/oauth-protected-resource/api/mcp/verein"
    meta = HttpClient().get(path).json()
    assert meta["resource"].endswith("/api/mcp/verein/")
    issuer = meta["authorization_servers"][0]
    assert issuer.endswith("/api/mcp/oauth")
    server = HttpClient().get("/.well-known/oauth-authorization-server/api/mcp/oauth").json()
    assert server["issuer"] == issuer
    assert server["code_challenge_methods_supported"] == ["S256"]
    assert server["token_endpoint_auth_methods_supported"] == ["none"]
    assert server["authorization_endpoint"].endswith("/ki/verbinden")
    # Auch unter /api (ohne Weiterleitung der Wurzel)
    same = HttpClient().get("/api/mcp/oauth/.well-known/oauth-authorization-server").json()
    assert same == server
    assert rpc("hpm_falsch", "initialize").status_code == 401


def test_anmeldung_eines_assistenten_prueft_rueckleitung(db):
    data = register(token_endpoint_auth_method="client_secret_basic")
    assert data["client_id"].startswith("hpmc_")
    assert data["token_endpoint_auth_method"] == "none"
    assert "client_secret" not in data
    for bad in ("http://assistent.example.org/cb", "javascript:alert(1)", "https://x.example/#f"):
        resp = HttpClient().post(
            "/api/mcp/oauth/register",
            json.dumps({"redirect_uris": [bad]}),
            content_type=JSON,
        )
        assert resp.status_code == 400, bad
    # Programm auf dem eigenen Rechner: Port darf wechseln
    local = register(redirect_uris=["http://127.0.0.1:33418/callback"])
    from mcpserver.oauth import redirect_ok

    client = McpClient.objects.get(client_id=local["client_id"])
    assert redirect_ok(client, "http://127.0.0.1:45001/callback")
    assert not redirect_ok(client, "http://127.0.0.1:45001/anders")


# --- Zustimmung ---


def test_zustimmung_nur_mit_zwei_faktor_recht_und_modul(club, site, editor, api):
    client_id = register()["client_id"]
    # Ohne zweiten Faktor: keine Zustimmung
    plain = api(editor)
    info = plain.get("/api/mcp/oauth/authorize/", params(client_id)).json()
    assert "Zwei-Faktor" in info["problem"]
    assert consent(plain, client_id, club.pk).status_code == 400
    c = with_mfa(editor, plain)
    info = c.get("/api/mcp/oauth/authorize/", params(client_id)).json()
    assert info["client"] == "Testassistent" and info["problem"] == ""
    assert info["redirect_host"] == "assistent.example.org"
    assert [u["id"] for u in info["units"]] == [club.pk]
    assert {s["scope"] for s in info["scopes"]} == {"webseite.lesen", "webseite.entwurf"}
    # Fremde Rückleitung: nie zurückleiten
    resp = consent(c, client_id, club.pk, redirect_uri="https://boese.example.org/cb")
    assert resp.status_code == 400 and resp.json()["redirect"] == ""
    # Ohne PKCE: zurück mit Fehler
    resp = consent(c, client_id, club.pk, code_challenge=None)
    assert resp.status_code == 400 and "error=invalid_request" in resp.json()["redirect"]
    # Modul aus: keine Einheit zur Auswahl
    club.enabled_modules = ["members", "events", "website"]
    club.save()
    assert c.get("/api/mcp/oauth/authorize/", params(client_id)).json()["units"] == []
    assert consent(c, client_id, club.pk).status_code == 400


def test_ohne_zusatzrecht_kein_verbinden(club, site):
    user = make_user("ki-ohne-recht@example.org")
    give_role(user, club, permissions=["website.manage"], name="Webseite")
    c = with_mfa(user)
    client_id = register()["client_id"]
    assert c.get("/api/mcp/oauth/authorize/", params(client_id)).json()["units"] == []
    assert consent(c, client_id, club.pk).status_code == 400


def test_ablehnen_leitet_mit_fehler_zurueck(club, site, editor):
    client_id = register()["client_id"]
    c = with_mfa(editor)
    resp = c.post(
        "/api/mcp/oauth/authorize/",
        {"params": params(client_id), "deny": True},
        content_type=JSON,
    )
    assert "error=access_denied" in resp.json()["redirect"]


# --- Schlüssel ---


def test_code_einmal_mit_pkce_und_mail(club, site, editor):
    client_id = register()["client_id"]
    c = with_mfa(editor)
    code = code_of(consent(c, client_id, club.pk))
    assert redeem(client_id, code, code_verifier="falsch-" * 8).status_code == 400
    code = code_of(consent(c, client_id, club.pk))
    mail.outbox.clear()
    resp = redeem(client_id, code)
    assert resp.status_code == 200, resp.content
    data = resp.json()
    assert data["access_token"].startswith("hpm_")
    assert data["refresh_token"].startswith("hpmr_")
    assert data["expires_in"] == 3600
    # Nur einmal einlösbar
    assert redeem(client_id, code).status_code == 400
    grant = McpGrant.objects.get(user=editor)
    assert data["access_token"] not in grant.access_hash
    assert any("KI-Assistent" in m.subject for m in mail.outbox)
    assert AuditEntry.objects.filter(organization=club, object_id=str(grant.pk)).exists()


def test_erneuern_und_kopie_erkennen(club, site, editor):
    first = connect(editor, club)
    form = {"grant_type": "refresh_token", "client_id": first["client_id"]}
    resp = HttpClient().post(
        "/api/mcp/oauth/token", {**form, "refresh_token": first["refresh_token"]}
    )
    assert resp.status_code == 200, resp.content
    second = resp.json()
    assert second["access_token"] != first["access_token"]
    # Alter Zugriffsschlüssel gilt nicht mehr, neuer schon
    assert rpc(first["access_token"], "ping").status_code == 401
    assert rpc(second["access_token"], "ping").status_code == 200
    # Alten Erneuerungsschlüssel noch einmal: Kopie, Verbindung endet
    resp = HttpClient().post(
        "/api/mcp/oauth/token", {**form, "refresh_token": first["refresh_token"]}
    )
    assert resp.status_code == 400
    assert rpc(second["access_token"], "ping").status_code == 401
    assert McpGrant.objects.get(user=editor).revoked_reason == "wiederverwendet"


def test_rechte_gelten_live(club, site, editor):
    token = connect(editor, club)["access_token"]
    assert rpc(token, "ping").status_code == 200
    role = editor.role_assignments.get().role
    role.permissions = ["website.content"]
    role.save()
    assert rpc(token, "ping").status_code == 401
    role.permissions = ["website.content", "mcp.connect"]
    role.save()
    assert rpc(token, "ping").status_code == 200
    # Passwort geändert / überall abgemeldet: Verbindung endet
    from accounts.models import User

    User.objects.filter(pk=editor.pk).update(auth_version=editor.auth_version + 1)
    assert rpc(token, "ping").status_code == 401


def test_mein_konto_listet_und_trennt(club, site, editor):
    token = connect(editor, club)["access_token"]
    c = with_mfa(editor)
    data = c.get("/api/me/mcp/").json()
    assert data["address"].endswith("/api/mcp/verein/")
    [row] = data["connections"]
    assert row["client"] == "Testassistent" and row["organization"] == club.name
    other = make_user("ki-fremd@example.org")
    assert HttpClient().delete(f"/api/me/mcp/{row['id']}/").status_code in (401, 403)
    fremd = HttpClient()
    fremd.force_login(other)
    assert fremd.delete(f"/api/me/mcp/{row['id']}/").status_code == 404
    assert c.delete(f"/api/me/mcp/{row['id']}/").status_code == 204
    assert c.get("/api/me/mcp/").json()["connections"] == []
    assert rpc(token, "ping").status_code == 401


def test_widerrufen_durch_assistent(club, site, editor):
    data = connect(editor, club)
    resp = HttpClient().post("/api/mcp/oauth/revoke", {"token": data["refresh_token"]})
    assert resp.status_code == 200
    assert rpc(data["access_token"], "ping").status_code == 401


# --- Werkzeuge der Webseite ---


def test_werkzeuge_je_bereich(club, site, editor):
    token = connect(editor, club, scope="webseite.lesen")["access_token"]
    resp = rpc(token, "initialize", {"protocolVersion": "2025-06-18"})
    assert resp.json()["result"]["serverInfo"]["name"] == "hubiplan-verein"
    names = {t["name"] for t in rpc(token, "tools/list").json()["result"]["tools"]}
    assert {"hilfe_suchen", "webseite_ansehen", "webseite_text_lesen"} <= names
    assert "webseite_text_aendern" not in names
    # Kein Werkzeug zum Veröffentlichen, für Zustand oder Domains
    assert not {n for n in names if "veroeffentlich" in n or "domain" in n}
    resp = rpc(token, "tools/call", {"name": "webseite_text_aendern", "arguments": {}})
    assert resp.json()["error"]["code"] == -32602


def test_text_als_entwurf_aendern(club, site, editor):
    token = connect(editor, club)["access_token"]
    text, failed = call(token, "webseite_texte")
    assert not failed and "greeting" in text
    greeting = WebsiteText.objects.get(website=site, kind="greeting")
    greeting.body = greeting.published_body = "Willkommen."
    greeting.title = greeting.published_title = "Hallo"
    greeting.save()
    text, failed = call(token, "webseite_text_lesen", nummer=greeting.pk)
    assert not failed and "Willkommen." in text
    text, failed = call(
        token, "webseite_text_aendern", nummer=greeting.pk, text="Herzlich willkommen!"
    )
    assert not failed, text
    greeting.refresh_from_db()
    # Nur der Entwurf ändert sich; öffentlich bleibt der alte Stand
    assert greeting.body == "Herzlich willkommen!"
    assert greeting.published_body == "Willkommen."
    entry = AuditEntry.objects.filter(organization=club, object_id=str(greeting.pk)).latest("id")
    assert entry.via == "KI-Assistent (Testassistent)"
    assert entry.user_id == editor.pk
    # Fremde Nummer: nicht gefunden
    _text, failed = call(token, "webseite_text_lesen", nummer=999999)
    assert failed


def test_textseite_anlegen_bleibt_unveroeffentlicht(club, site, editor):
    token = connect(editor, club)["access_token"]
    text, failed = call(
        token, "webseite_textseite_anlegen", titel="Anfahrt", adresse="anfahrt", text="Am Markt."
    )
    assert not failed, text
    page = WebsiteText.objects.get(website=site, slug="anfahrt")
    assert page.kind == "page" and not page.is_published
    _text, failed = call(token, "webseite_textseite_anlegen", titel="Doppelt", adresse="anfahrt")
    assert failed


def test_startseite_nur_inhalt(club, site, editor):
    token = connect(editor, club)["access_token"]
    text, failed = call(token, "startseite_ansehen")
    assert not failed and "c:t1" in text and "Seit 1900." in text
    text, failed = call(
        token, "startseite_abschnitt_aendern", schluessel="c:t1", inhalt={"text": "Seit 1920."}
    )
    assert not failed, text
    site.refresh_from_db()
    [own] = [s for s in site.draft["home_sections"] if s["key"] == "c:t1"]
    assert own["data"]["text"] == "Seit 1920." and own["data"]["title"] == "Über uns"
    # Veröffentlichter Stand bleibt
    assert [s for s in site.home_sections if s["key"] == "c:t1"][0]["data"]["text"] == "Seit 1900."
    _text, failed = call(
        token, "startseite_abschnitt_aendern", schluessel="greeting", inhalt={"x": 1}
    )
    assert failed


def test_vorschau_und_pruefen(club, site, editor, settings):
    token = connect(editor, club)["access_token"]
    text, failed = call(token, "webseite_vorschau")
    assert not failed and "keine Adresse" in text
    settings.WEBSITE_PUBLIC_URL = "https://web.example.org/webseite/"
    text, failed = call(token, "webseite_vorschau")
    assert not failed and "http" in text
    text, failed = call(token, "webseite_pruefen")
    assert not failed and "pruefpunkte" in text
    text, failed = call(token, "webseite_ansehen")
    assert not failed and club.name in text


def test_nur_eigene_einheit(club, site, editor, orgs):
    other = orgs["b"]
    other.enabled_modules = ["members", "events", "website", "mcp"]
    other.save()
    Website.objects.create(organization=other, public_key="mcp-b")
    token = connect(editor, club)["access_token"]
    with_other = WebsiteText.objects.create(
        organization=other,
        website=Website.objects.get(organization=other),
        kind="page",
        slug="geheim",
        title="Geheim",
    )
    _text, failed = call(token, "webseite_text_lesen", nummer=with_other.pk)
    assert failed


def test_abgeschaltet(club, site, editor, settings):
    token = connect(editor, club)["access_token"]
    settings.MCP_ENABLED = False
    assert rpc(token, "ping").status_code == 404
    assert HttpClient().get("/.well-known/oauth-protected-resource").status_code == 404


# --- Gesamtaudit 11.11., S-06: Zustimmungsseite zeigt, wohin die Freigabe geht ---


def test_art_der_rueckleitung(settings):
    settings.MCP_KNOWN_REDIRECT_HOSTS = ["claude.ai", "assistent.example.org"]
    assert redirect_kind("https://claude.ai/api/mcp/auth_callback") == "bekannt"
    assert redirect_kind("https://app.assistent.example.org/cb") == "bekannt"
    # Nur ganze Namensteile zählen: kein Unterlaufen mit ähnlichem Namen
    assert redirect_kind("https://claude.ai.boese.example/cb") == "web"
    assert redirect_kind("https://fakeclaude.ai/cb") == "web"
    assert redirect_kind("http://127.0.0.1:45001/callback") == "rechner"
    assert redirect_kind("de.example.assistent:/cb") == "rechner"


def test_zustimmungsseite_nennt_art_und_fruehere_verbindung(settings, club, site, editor):
    settings.MCP_KNOWN_REDIRECT_HOSTS = ["claude.ai"]
    c = with_mfa(editor)
    client_id = register()["client_id"]
    info = c.get("/api/mcp/oauth/authorize/", params(client_id)).json()
    assert info["redirect_host"] == "assistent.example.org"
    assert info["redirect_kind"] == "web"
    assert info["connected_before"] is False
    settings.MCP_KNOWN_REDIRECT_HOSTS = ["example.org"]
    assert c.get("/api/mcp/oauth/authorize/", params(client_id)).json()["redirect_kind"] == (
        "bekannt"
    )
    # Nach einer Verbindung mit demselben Assistenten: keine Warnung mehr nötig
    first = connect(editor, club)
    info = c.get("/api/mcp/oauth/authorize/", params(first["client_id"])).json()
    assert info["connected_before"] is True


def test_nie_genutzte_anmeldungen_nach_einem_tag_weg():
    old = register()["client_id"]
    with rls_bypass():
        McpClient.objects.filter(client_id=old).update(
            created_at=timezone.now() - datetime.timedelta(hours=25)
        )
    fresh = register()["client_id"]
    with rls_bypass():
        ids = set(McpClient.objects.values_list("client_id", flat=True))
    assert old not in ids and fresh in ids
