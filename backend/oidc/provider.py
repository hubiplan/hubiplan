"""HUBIplan als Anmeldedienst nach OpenID Connect (Authorization Code Flow).

Bewusst klein gehalten, damit es sich prüfen lässt:

- nur ``response_type=code``, nur vertrauliche Clients (mit Geheimnis),
- Rückleitung nur an die eingetragene Nextcloud (genauer Vergleich),
- PKCE nur mit S256 (``plain`` wird abgelehnt), optional wie in OAuth 2.0 für Clients
  mit Geheimnis,
- Code 60 Sekunden gültig und nur einmal einlösbar, Zugriffsschlüssel 5 Minuten,
  keine Refresh-Token; beides nur im Cache, nie in der Datenbank,
- ID-Token mit RS256 (``keys``), Angaben siehe ``claims``,
- Abmelden von der Nextcloud (RP-initiated Logout, ``end_session``): Danach meldet HUBIplan
  diese Sitzung nicht mehr still bei derselben Nextcloud an, sondern fragt einmal nach.

Die Bestätigung, wie sich die Sitzung angemeldet hat (``amr``, ``auth_time``), kommt aus
der Sitzung wie beim Verbund (``peering.sso.session_auth``). Ist beim Dienst die
Zwei-Faktor-Anmeldung verlangt, muss die Sitzung mit zweitem Faktor entstanden sein.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from urllib.parse import unquote, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.translation import gettext

from core.tenancy import rls_bypass

from . import claims, keys, nc_accounts
from .models import Client

CODE_SECONDS = 60
TOKEN_SECONDS = 300
SCOPES = ("openid", "profile", "email", "groups")
CODE_PREFIX = "oidc:code:"
TOKEN_PREFIX = "oidc:token:"  # noqa: S105 (Cache-Schlüssel, kein Passwort)
MAX_PARAM = 500
MAX_HINT = 8000
# Sitzungsschlüssel: client_id -> Zeitpunkt der Abmeldung von dieser Nextcloud
LOGGED_OUT_KEY = "oidc_logged_out"
# Diese Angaben von ``prompt`` verlangen eine sichtbare Bestätigung statt stiller Anmeldung
PROMPT_ASK = ("login", "consent", "select_account")


class AuthorizeError(Exception):
    """Fehler bei der Anmeldung.

    ``redirect``: Adresse, an die der Browser mit dem Fehler zurück soll (leer: Rückleitung
    nicht vertrauenswürdig, dann nur Meldung in HUBIplan anzeigen).
    """

    def __init__(self, message: str, redirect: str = "", back: str = ""):
        super().__init__(message)
        self.message = message
        self.redirect = redirect
        # Adresse der Nextcloud für den Knopf „Zurück“
        self.back = back


class ConfirmNeeded(Exception):
    """Nicht still anmelden: Die Person soll die Anmeldung bei der Nextcloud bestätigen."""

    def __init__(self, name: str):
        super().__init__(name)
        self.name = name


class TokenError(Exception):
    def __init__(self, error: str, description: str = "", status: int = 400):
        super().__init__(description or error)
        self.error = error
        self.description = description
        self.status = status


def issuer() -> str:
    base = getattr(settings, "OIDC_ISSUER", "") or f"{settings.FRONTEND_URL.rstrip('/')}/api/oidc"
    return base.rstrip("/")


def discovery() -> dict:
    iss = issuer()
    front = settings.FRONTEND_URL.rstrip("/")
    return {
        "issuer": iss,
        "authorization_endpoint": f"{front}/oidc/anmelden",
        "end_session_endpoint": f"{front}/oidc/abmelden",
        "token_endpoint": f"{iss}/token",
        "userinfo_endpoint": f"{iss}/userinfo",
        "jwks_uri": f"{iss}/jwks",
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code"],
        "subject_types_supported": ["pairwise"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "scopes_supported": list(SCOPES),
        "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
        "code_challenge_methods_supported": ["S256"],
        "claims_supported": [
            "sub",
            "iss",
            "aud",
            "exp",
            "iat",
            "auth_time",
            "nonce",
            "amr",
            "name",
            "given_name",
            "family_name",
            "preferred_username",
            "email",
            "groups",
        ],
        "authorization_response_iss_parameter_supported": True,
    }


def jwks() -> dict:
    return {"keys": keys.public_keys()}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def find_client(client_id: str) -> Client | None:
    client_id = str(client_id or "")[:64]
    if not client_id:
        return None
    with rls_bypass():
        return (
            Client.objects.select_related("organization")
            .filter(client_id=client_id, is_active=True, organization__is_active=True)
            .first()
        )


def _with_query(url: str, params: dict) -> str:
    parts = urlsplit(url)
    query = urlencode({k: v for k, v in params.items() if v})
    joined = f"{parts.query}&{query}" if parts.query else query
    return urlunsplit((parts.scheme, parts.netloc, parts.path, joined, ""))


def _param(params, name: str, limit: int = MAX_PARAM) -> str:
    value = params.get(name)
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "")[:limit]


def describe(params) -> dict:
    """Für die Seite in HUBIplan: welcher Dienst fragt an?"""
    client = find_client(_param(params, "client_id"))
    if client is None or _param(params, "redirect_uri") not in client.redirect_uris:
        raise AuthorizeError(gettext("Diese Anmeldung kennt HUBIplan nicht."))
    return {"name": client.name, "organization": client.organization.name, "url": client.base_url}


def authorize(request, params) -> str:
    """Anmeldung für den angemeldeten Benutzer bestätigen; liefert die Rückleitung mit Code."""
    from peering.sso import session_auth

    client = find_client(_param(params, "client_id"))
    redirect_uri = _param(params, "redirect_uri")
    if client is None or redirect_uri not in client.redirect_uris:
        # Unbekannte Rückleitung nie benutzen (offene Weiterleitung)
        raise AuthorizeError(gettext("Diese Anmeldung kennt HUBIplan nicht."))
    state = _param(params, "state")

    def back(error: str, description: str = "") -> AuthorizeError:
        url = _with_query(
            redirect_uri,
            {"error": error, "error_description": description, "state": state, "iss": issuer()},
        )
        return AuthorizeError(description or error, redirect=url, back=client.base_url)

    if _param(params, "response_type") != "code":
        raise back("unsupported_response_type")
    scopes = _param(params, "scope").split()
    if "openid" not in scopes:
        raise back("invalid_scope", "openid fehlt")
    challenge = _param(params, "code_challenge")
    method = _param(params, "code_challenge_method") or ("plain" if challenge else "")
    if challenge and method != "S256":
        raise back("invalid_request", "Nur PKCE mit S256")
    if not challenge and client.require_pkce:
        # Fachfrage FQ26: ohne PKCE ließe sich ein abgefangener Code einlösen
        raise back("invalid_request", "PKCE (S256) ist nötig")
    prompts = _param(params, "prompt").split()
    if "none" in prompts and not request.user.is_authenticated:
        raise back("login_required")

    user = request.user
    auth = session_auth(request)
    if _must_confirm(request, client, prompts, auth) and not _param(params, "confirm"):
        if "none" in prompts:
            raise back("interaction_required")
        raise ConfirmNeeded(client.name)
    try:
        claims.profile(client, user)
    except claims.NotAllowed as exc:
        raise AuthorizeError(str(exc), back=client.base_url) from exc
    if client.require_mfa and "mfa" not in auth["amr"]:
        from accounts.mfa_policy import has_mfa

        if has_mfa(user):
            message = gettext(
                "Für „{name}“ ist die Zwei-Faktor-Anmeldung nötig. Bitte melde dich bei "
                "HUBIplan ab und mit Passwort und Code wieder an."
            )
        else:
            message = gettext(
                "Für „{name}“ ist die Zwei-Faktor-Anmeldung nötig. Richte sie unter "
                "„Mein Konto“ ein und versuche es dann erneut."
            )
        raise AuthorizeError(message.format(name=client.name), back=client.base_url)

    _forget_logout(request, client)
    code = secrets.token_urlsafe(32)
    cache.set(
        CODE_PREFIX + _hash(code),
        {
            "client_id": client.client_id,
            "user_id": user.pk,
            "auth_version": user.auth_version,
            "redirect_uri": redirect_uri,
            "nonce": _param(params, "nonce"),
            "challenge": challenge,
            "scope": [s for s in scopes if s in SCOPES],
            "auth_time": auth["auth_time"] or int(time.time()),
            "amr": auth["amr"],
        },
        CODE_SECONDS,
    )
    return _with_query(redirect_uri, {"code": code, "state": state, "iss": issuer()})


def _logged_out(request) -> dict:
    value = request.session.get(LOGGED_OUT_KEY)
    return dict(value) if isinstance(value, dict) else {}


def _must_confirm(request, client: Client, prompts: list[str], auth: dict) -> bool:
    """Bestätigen lassen, wenn die Nextcloud es verlangt oder man sich dort abgemeldet hat.

    Eine Abmeldung zählt nur, bis man sich bei HUBIplan neu anmeldet (``auth_time`` danach).
    """
    if any(p in PROMPT_ASK for p in prompts):
        return True
    at = _logged_out(request).get(client.client_id)
    return at is not None and float(at) >= float(auth.get("auth_time") or 0)


def _forget_logout(request, client: Client) -> None:
    marks = _logged_out(request)
    if marks.pop(client.client_id, None) is not None:
        request.session[LOGGED_OUT_KEY] = marks


def _client_from_hint(hint: str) -> Client | None:
    """``aud`` aus einem ID-Token (``id_token_hint``) lesen.

    Die Signatur wird nicht geprüft: Das Ergebnis dient nur dazu, den Dienst zu finden. Die
    Rückleitung prüft ``end_session`` ohnehin gegen die eingetragene Adresse.
    """
    try:
        body = hint.split(".")[1]
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except (IndexError, ValueError, UnicodeDecodeError):
        return None
    aud = data.get("aud") if isinstance(data, dict) else None
    if isinstance(aud, list):
        aud = aud[0] if len(aud) == 1 else ""
    return find_client(str(aud or ""))


def _same_site(url: str, base: str) -> bool:
    one, two = urlsplit(url), urlsplit(base)
    return bool(one.scheme and one.netloc) and (one.scheme, one.netloc.lower()) == (
        two.scheme,
        two.netloc.lower(),
    )


def end_session(request, params) -> dict:
    """Abmelden von der Nextcloud (OpenID Connect RP-Initiated Logout 1.0).

    Merkt sich in der Sitzung, dass man sich von dieser Nextcloud abgemeldet hat; die nächste
    Anmeldung dort geht dann nicht mehr still, sondern erst nach einem Klick. Zurück geht es
    nur an die eingetragene Nextcloud (gleiche Herkunft), sonst an ihre Startseite.
    """
    client = find_client(_param(params, "client_id"))
    # Ein ID-Token ist länger als die übrigen Angaben
    hint = _param(params, "id_token_hint", MAX_HINT)
    if client is None and hint:
        client = _client_from_hint(hint)
    if client is None:
        return {"name": "", "back": "", "logged_in": request.user.is_authenticated}
    if request.user.is_authenticated:
        marks = _logged_out(request)
        marks[client.client_id] = time.time()
        request.session[LOGGED_OUT_KEY] = marks
    target = _param(params, "post_logout_redirect_uri")
    if not target or not _same_site(target, client.base_url):
        target = client.base_url
    state = _param(params, "state")
    if state:
        target = _with_query(target, {"state": state})
    return {"name": client.name, "back": target, "logged_in": request.user.is_authenticated}


def _client_credentials(request) -> tuple[str, str]:
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if header.lower().startswith("basic "):
        try:
            raw = base64.b64decode(header[6:].strip(), validate=True).decode()
        except (ValueError, UnicodeDecodeError) as exc:
            raise TokenError("invalid_client", status=401) from exc
        client_id, _, secret = raw.partition(":")
        # RFC 6749 2.3.1: beide Teile sind formular-kodiert
        return unquote(client_id.replace("+", " ")), unquote(secret.replace("+", " "))
    return str(request.POST.get("client_id") or ""), str(request.POST.get("client_secret") or "")


def _authenticate_client(request) -> Client:
    client_id, secret = _client_credentials(request)
    client = find_client(client_id)
    if client is None or not client.check_secret(secret):
        raise TokenError("invalid_client", status=401)
    return client


def _user(user_id):
    from accounts.models import User

    return User.objects.filter(pk=user_id, is_active=True).first()


def _pkce_ok(challenge: str, verifier: str) -> bool:
    if not challenge:
        return True
    digest = keys.b64url(hashlib.sha256(verifier.encode()).digest())
    return secrets.compare_digest(digest, challenge)


def token(request) -> dict:
    client = _authenticate_client(request)
    if request.POST.get("grant_type") != "authorization_code":
        raise TokenError("unsupported_grant_type")
    code = str(request.POST.get("code") or "")[:MAX_PARAM]
    key = CODE_PREFIX + _hash(code)
    data = cache.get(key) if code else None
    # Nur einmal einlösbar: Wer den Eintrag nicht selbst löscht, war zu spät
    if data is None or not cache.delete(key):
        raise TokenError("invalid_grant")
    if data["client_id"] != client.client_id or data["redirect_uri"] != str(
        request.POST.get("redirect_uri") or ""
    ):
        raise TokenError("invalid_grant")
    if not _pkce_ok(data["challenge"], str(request.POST.get("code_verifier") or "")):
        raise TokenError("invalid_grant")
    user = _user(data["user_id"])
    if user is None or data.get("auth_version", 0) != user.auth_version:
        raise TokenError("invalid_grant")
    try:
        prof = claims.profile(client, user)
    except claims.NotAllowed as exc:
        raise TokenError("invalid_grant") from exc
    nc_accounts.remember_login(client, user, prof)

    now = int(time.time())
    id_claims = {
        "iss": issuer(),
        "sub": claims.subject(client, user),
        "aud": client.client_id,
        "azp": client.client_id,
        "iat": now,
        "exp": now + TOKEN_SECONDS,
        "auth_time": data["auth_time"],
        "amr": data["amr"],
        **_scoped(prof, data["scope"]),
    }
    if data["nonce"]:
        id_claims["nonce"] = data["nonce"]
    access = secrets.token_urlsafe(32)
    cache.set(
        TOKEN_PREFIX + _hash(access),
        {
            "client_id": client.client_id,
            "user_id": user.pk,
            "scope": data["scope"],
            "auth_version": user.auth_version,
        },
        TOKEN_SECONDS,
    )
    with rls_bypass():
        Client.objects.filter(pk=client.pk).update(last_used_at=timezone.now())
    return {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": TOKEN_SECONDS,
        "scope": " ".join(data["scope"]),
        "id_token": keys.jwt(id_claims),
    }


def _scoped(prof: claims.Profile, scope: list[str]) -> dict:
    out: dict = {}
    if "profile" in scope:
        out.update(name=prof.name, given_name=prof.given_name, family_name=prof.family_name)
        if prof.username:
            out["preferred_username"] = prof.username
    if "email" in scope:
        out["email"] = prof.email
    if "groups" in scope:
        out["groups"] = prof.groups
    return out


def userinfo(request) -> dict:
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header.lower().startswith("bearer "):
        raise TokenError("invalid_token", status=401)
    data = cache.get(TOKEN_PREFIX + _hash(header[7:].strip()))
    if data is None:
        raise TokenError("invalid_token", status=401)
    client = find_client(data["client_id"])
    user = _user(data["user_id"])
    if client is None or user is None or data.get("auth_version", 0) != user.auth_version:
        raise TokenError("invalid_token", status=401)
    try:
        prof = claims.profile(client, user)
    except claims.NotAllowed as exc:
        raise TokenError("invalid_token", status=401) from exc
    return {"sub": claims.subject(client, user), **_scoped(prof, data["scope"])}
