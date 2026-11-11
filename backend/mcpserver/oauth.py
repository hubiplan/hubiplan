"""Anmeldung der KI-Assistenten nach OAuth 2.1 (Stufe 1a, docs/mcp.md).

So wie die MCP-Spezifikation es verlangt, und bewusst klein:

- Assistenten melden sich selbst an (Dynamic Client Registration, RFC 7591), bekommen nur
  eine Kennung und kein Geheimnis („öffentlicher Client“),
- nur ``response_type=code`` mit PKCE (S256), Rückleitung genau wie angemeldet (bei
  Rückleitung an den eigenen Rechner ``127.0.0.1``/``localhost`` mit beliebigem Port),
- zustimmen kann nur, wer mit zweitem Faktor angemeldet ist und in der gewählten Einheit
  das Zusatzrecht „KI-Assistenten verbinden“ hat,
- Code 60 Sekunden und nur einmal, Zugriffsschlüssel ``hpm_`` eine Stunde, Erneuerung
  höchstens 30 Tage und nach 14 Tagen ohne Nutzung vorbei; wer einen alten
  Erneuerungsschlüssel noch einmal benutzt, beendet die Verbindung (Kopie).

Alle Adressen gehen von der aufgerufenen Adresse aus (``base_url``), damit eine Instanz
mit mehreren Adressen überall dieselbe Anmeldung anbietet.
"""

from __future__ import annotations

import datetime
import hashlib
import ipaddress
import re
import secrets
from urllib.parse import urlencode, urlsplit, urlunsplit

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy

from access.catalog import MCP_CONNECT, WEBCONTENT_VIEW, WEBSITE_VIEW
from changes import tracking
from core.tenancy import rls_bypass
from organizations.addresses import base_url

from .models import (
    ACCESS_LIFETIME,
    ACCESS_PREFIX,
    GRANT_LIFETIME,
    REFRESH_PREFIX,
    McpClient,
    McpGrant,
    hash_token,
)

# Modul „KI-Assistenten“ je Einheit, standardmäßig aus
MODULE = "mcp"
ISSUER_PATH = "/api/mcp/oauth"
RESOURCE_PATH = "/api/mcp/verein/"
CONSENT_PATH = "/ki/verbinden"
CODE_SECONDS = 60
CODE_PREFIX = "mcp:code:"
MAX_PARAM = 500
MAX_REDIRECTS = 5
# Nicht genutzte Anmeldungen von Assistenten nach einer Woche wegräumen
CLIENT_UNUSED = datetime.timedelta(days=7)

# Bereiche (scopes): Hilfe ist immer dabei. „entwurf“ schließt „lesen“ ein.
SCOPE_READ = "webseite.lesen"
SCOPE_DRAFT = "webseite.entwurf"
SCOPES = {
    SCOPE_READ: gettext_lazy("Webseite lesen: Einstellungen, Texte und Startseite ansehen"),
    SCOPE_DRAFT: gettext_lazy(
        "Webseite als Entwurf bearbeiten: Texte und Inhalte der Startseite ändern, neue "
        "Textseiten anlegen (veröffentlicht wird nur in HUBIplan)"
    ),
}
DEFAULT_SCOPES = (SCOPE_READ, SCOPE_DRAFT)
# Schemata, die nie als Rückleitung taugen
BAD_SCHEMES = {"javascript", "data", "file", "vbscript", "about", "blob", "ftp", "ws", "wss"}
SCHEME = re.compile(r"^[a-z][a-z0-9+.-]{1,40}$")


class OAuthError(Exception):
    def __init__(self, error: str, description: str = "", status: int = 400):
        super().__init__(description or error)
        self.error = error
        self.description = description
        self.status = status

    def body(self) -> dict:
        data = {"error": self.error}
        if self.description:
            data["error_description"] = self.description
        return data


class ConsentError(Exception):
    """Fehler auf der Seite „KI-Assistent verbinden“.

    ``redirect``: Rückleitung mit Fehler an den Assistenten (leer: Rückleitung unbekannt,
    dann nur die Meldung in HUBIplan zeigen)."""

    def __init__(self, message: str, redirect: str = ""):
        super().__init__(message)
        self.message = message
        self.redirect = redirect


# --- Adressen und Beschreibungen ---


def base(request) -> str:
    return base_url(request=request)


def issuer(request) -> str:
    return base(request) + ISSUER_PATH


def resource(request) -> str:
    return base(request) + RESOURCE_PATH


def resource_metadata_url(request) -> str:
    return base(request) + "/.well-known/oauth-protected-resource" + RESOURCE_PATH.rstrip("/")


def resource_metadata(request) -> dict:
    """RFC 9728: wo sich ein Assistent für ``/api/mcp/verein/`` anmeldet."""
    return {
        "resource": resource(request),
        "authorization_servers": [issuer(request)],
        "scopes_supported": list(SCOPES),
        "bearer_methods_supported": ["header"],
        "resource_name": "HUBIplan",
        "resource_documentation": base(request) + "/hilfe/ki-assistent-verbinden",
    }


def server_metadata(request) -> dict:
    """RFC 8414: Adressen der Anmeldung."""
    iss = issuer(request)
    return {
        "issuer": iss,
        "authorization_endpoint": base(request) + CONSENT_PATH,
        "token_endpoint": f"{iss}/token",
        "registration_endpoint": f"{iss}/register",
        "revocation_endpoint": f"{iss}/revoke",
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "revocation_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": list(SCOPES),
        "authorization_response_iss_parameter_supported": True,
        "service_documentation": base(request) + "/hilfe/ki-assistent-verbinden",
    }


def scope_labels(scopes) -> list[dict]:
    return [{"scope": s, "label": str(SCOPES[s])} for s in SCOPES if s in scopes]


def clean_scopes(value) -> list[str]:
    """Leere Angabe: alle Bereiche. Unbekannte fallen weg; „entwurf“ zieht „lesen“ mit."""
    if isinstance(value, str):
        value = value.split()
    wanted = [s for s in value or [] if s in SCOPES] if value else list(DEFAULT_SCOPES)
    if SCOPE_DRAFT in wanted and SCOPE_READ not in wanted:
        wanted.append(SCOPE_READ)
    return [s for s in SCOPES if s in wanted]


# --- Anmeldung eines Assistenten (RFC 7591) ---


def _loopback(host: str | None) -> bool:
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def clean_redirect(value) -> str:
    uri = str(value or "").strip()
    if not uri or len(uri) > MAX_PARAM:
        raise OAuthError("invalid_redirect_uri", "redirect_uri fehlt oder ist zu lang")
    parts = urlsplit(uri)
    scheme = parts.scheme.lower()
    if parts.fragment or parts.username or parts.password:
        raise OAuthError("invalid_redirect_uri", "redirect_uri ohne Fragment und Zugangsdaten")
    if scheme == "https":
        if not parts.hostname:
            raise OAuthError("invalid_redirect_uri", "redirect_uri braucht einen Host")
    elif scheme == "http":
        # Nur an den eigenen Rechner (RFC 8252, Programme auf dem Rechner)
        if not _loopback(parts.hostname):
            raise OAuthError("invalid_redirect_uri", "http nur für 127.0.0.1 oder localhost")
    elif not SCHEME.match(scheme) or scheme in BAD_SCHEMES:
        # Eigenes Schema eines Programms auf dem Rechner (RFC 8252, 7.1)
        raise OAuthError("invalid_redirect_uri", "Dieses Schema ist nicht erlaubt")
    return uri


def redirect_ok(client: McpClient, uri: str) -> bool:
    if uri in client.redirect_uris:
        return True
    parts = urlsplit(uri)
    if parts.scheme != "http" or not _loopback(parts.hostname):
        return False
    # Rückleitung an den eigenen Rechner: Port darf wechseln (RFC 8252, 7.3)
    for known in client.redirect_uris:
        k = urlsplit(known)
        if (
            k.scheme == "http"
            and k.hostname == parts.hostname
            and k.path == parts.path
            and k.query == parts.query
        ):
            return True
    return False


def register(data) -> dict:
    if not isinstance(data, dict):
        raise OAuthError("invalid_client_metadata", "JSON-Objekt erwartet")
    uris = data.get("redirect_uris")
    if not isinstance(uris, list) or not 1 <= len(uris) <= MAX_REDIRECTS:
        raise OAuthError("invalid_redirect_uri", "1 bis 5 redirect_uris angeben")
    uris = [clean_redirect(u) for u in uris]
    grant_types = data.get("grant_types") or ["authorization_code", "refresh_token"]
    if not isinstance(grant_types, list) or "authorization_code" not in grant_types:
        raise OAuthError("invalid_client_metadata", "grant_types braucht authorization_code")
    response_types = data.get("response_types") or ["code"]
    if response_types != ["code"]:
        raise OAuthError("invalid_client_metadata", "Nur response_types code")
    name = str(data.get("client_name") or "").strip()[:100] or gettext("KI-Assistent")
    now = timezone.now()
    with rls_bypass():
        # Nie genutzte Anmeldungen wegräumen (jeder darf sich anmelden)
        McpClient.objects.filter(created_at__lt=now - CLIENT_UNUSED, grants__isnull=True).delete()
        client = McpClient.objects.create(name=name, redirect_uris=uris)
    return {
        "client_id": client.client_id,
        "client_id_issued_at": int(client.created_at.timestamp()),
        "client_name": client.name,
        "redirect_uris": client.redirect_uris,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        # Öffentlicher Client: kein Geheimnis, Schutz durch PKCE
        "token_endpoint_auth_method": "none",
    }


def find_client(client_id) -> McpClient | None:
    client_id = str(client_id or "")[:64]
    if not client_id:
        return None
    with rls_bypass():
        return McpClient.objects.filter(client_id=client_id).first()


# --- Zustimmung (Seite „KI-Assistent verbinden“) ---


def _param(params, name: str) -> str:
    value = params.get(name)
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "")[:MAX_PARAM]


def _with_query(url: str, params: dict) -> str:
    parts = urlsplit(url)
    query = urlencode({k: v for k, v in params.items() if v})
    joined = f"{parts.query}&{query}" if parts.query else query
    return urlunsplit((parts.scheme, parts.netloc, parts.path, joined, ""))


def units_for(user) -> list:
    """Einheiten, für die der Benutzer einen Assistenten verbinden darf."""
    from access.modules import module_on
    from access.permissions import organizations_for

    units = [
        org
        for org, perms in organizations_for(user)
        if MCP_CONNECT in perms
        and {WEBCONTENT_VIEW, WEBSITE_VIEW} & perms
        and module_on(org, MODULE)
    ]
    return sorted(units, key=lambda o: o.name.lower())


def _checked(request, params) -> tuple[McpClient, str, str, list[str]]:
    """Anfrage des Assistenten prüfen: Client, Rückleitung, ``state``, Bereiche."""
    client = find_client(_param(params, "client_id"))
    redirect_uri = _param(params, "redirect_uri")
    if client is None or not redirect_ok(client, redirect_uri):
        # Unbekannte Rückleitung nie benutzen (offene Weiterleitung)
        raise ConsentError(gettext("Diesen KI-Assistenten kennt HUBIplan nicht."))
    state = _param(params, "state")

    def back(error: str, description: str = "") -> ConsentError:
        url = _with_query(
            redirect_uri,
            {
                "error": error,
                "error_description": description,
                "state": state,
                "iss": issuer(request),
            },
        )
        return ConsentError(description or error, redirect=url)

    if _param(params, "response_type") != "code":
        raise back("unsupported_response_type")
    if not _param(params, "code_challenge") or _param(params, "code_challenge_method") != "S256":
        raise back("invalid_request", "PKCE mit S256 ist nötig")
    wanted = _param(params, "resource").rstrip("/")
    if wanted and wanted != resource(request).rstrip("/"):
        raise back("invalid_target", "Unbekannte Ressource")
    scopes = clean_scopes(_param(params, "scope"))
    if not scopes:
        raise back("invalid_scope")
    return client, redirect_uri, state, scopes


def _mfa_problem(request, user) -> str:
    from accounts.mfa_policy import has_mfa
    from peering.sso import session_auth

    if not has_mfa(user):
        return gettext(
            "Für KI-Assistenten ist die Zwei-Faktor-Anmeldung nötig. Richte sie unter "
            "„Mein Konto“ ein und versuche es dann erneut."
        )
    if "mfa" not in session_auth(request)["amr"]:
        return gettext(
            "Für KI-Assistenten ist die Zwei-Faktor-Anmeldung nötig. Bitte melde dich bei "
            "HUBIplan ab und mit Passwort und Code wieder an."
        )
    return ""


def describe(request, params) -> dict:
    client, redirect_uri, _state, scopes = _checked(request, params)
    user = request.user
    return {
        "client": client.name,
        "redirect_host": urlsplit(redirect_uri).hostname or urlsplit(redirect_uri).scheme,
        "scopes": scope_labels(scopes),
        "units": [{"id": o.pk, "name": o.name} for o in units_for(user)],
        "problem": _mfa_problem(request, user),
    }


def authorize(request, params, organization_id) -> str:
    """Zustimmung der angemeldeten Person; liefert die Rückleitung mit Code."""
    client, redirect_uri, state, scopes = _checked(request, params)
    user = request.user
    problem = _mfa_problem(request, user)
    if problem:
        raise ConsentError(problem)
    unit = next((o for o in units_for(user) if str(o.pk) == str(organization_id)), None)
    if unit is None:
        raise ConsentError(gettext("Für diese Einheit darfst du keinen KI-Assistenten verbinden."))
    code = secrets.token_urlsafe(32)
    cache.set(
        CODE_PREFIX + hash_token(code),
        {
            "client_id": client.client_id,
            "user_id": user.pk,
            "auth_version": user.auth_version,
            "organization_id": unit.pk,
            "redirect_uri": redirect_uri,
            "challenge": _param(params, "code_challenge"),
            "scopes": scopes,
        },
        CODE_SECONDS,
    )
    return _with_query(redirect_uri, {"code": code, "state": state, "iss": issuer(request)})


def denied(request, params) -> str:
    """Abgelehnt: Rückleitung mit ``access_denied``."""
    _client, redirect_uri, state, _scopes = _checked(request, params)
    return _with_query(
        redirect_uri, {"error": "access_denied", "state": state, "iss": issuer(request)}
    )


# --- Schlüssel ausstellen und erneuern ---


def _b64url(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _pkce_ok(challenge: str, verifier: str) -> bool:
    if not challenge or not 43 <= len(verifier) <= 128:
        return False
    digest = _b64url(hashlib.sha256(verifier.encode()).digest())
    return secrets.compare_digest(digest, challenge)


def _answer(grant: McpGrant, access: str, refresh: str) -> dict:
    return {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": int(ACCESS_LIFETIME.total_seconds()),
        "refresh_token": refresh,
        "scope": " ".join(grant.scopes),
    }


def _user(user_id):
    from accounts.models import User

    return User.objects.filter(pk=user_id, is_active=True).first()


def _post(request, name: str) -> str:
    return str(request.POST.get(name) or "")[:MAX_PARAM]


def token(request) -> dict:
    grant_type = _post(request, "grant_type")
    if grant_type == "authorization_code":
        return _from_code(request)
    if grant_type == "refresh_token":
        return _refresh(request)
    raise OAuthError("unsupported_grant_type")


def _from_code(request) -> dict:
    from organizations.models import Organization

    client = find_client(_post(request, "client_id"))
    if client is None:
        raise OAuthError("invalid_client", status=401)
    code = _post(request, "code")
    key = CODE_PREFIX + hash_token(code)
    data = cache.get(key) if code else None
    # Nur einmal einlösbar: Wer den Eintrag nicht selbst löscht, war zu spät
    if data is None or not cache.delete(key):
        raise OAuthError("invalid_grant")
    if data["client_id"] != client.client_id or data["redirect_uri"] != _post(
        request, "redirect_uri"
    ):
        raise OAuthError("invalid_grant")
    if not _pkce_ok(data["challenge"], _post(request, "code_verifier")):
        raise OAuthError("invalid_grant", "code_verifier passt nicht")
    user = _user(data["user_id"])
    if user is None or data["auth_version"] != user.auth_version:
        raise OAuthError("invalid_grant")
    now = timezone.now()
    with tracking.suppress(), rls_bypass(), transaction.atomic():
        org = Organization.objects.get(pk=data["organization_id"])
        grant = McpGrant(
            user=user,
            organization=org,
            client=client,
            scopes=data["scopes"],
            auth_version=user.auth_version,
            expires_at=now + GRANT_LIFETIME,
            last_used_at=now,
        )
        access, refresh = grant.issue()
        grant.save()
        McpClient.objects.filter(pk=client.pk).update(last_used_at=now)
        from audit.log import record

        record(org, user, "create", grant, {"KI-Assistent": [None, client.name]})
    from . import notify

    notify.connected(grant)
    return _answer(grant, access, refresh)


def _refresh(request) -> dict:
    client = find_client(_post(request, "client_id"))
    if client is None:
        raise OAuthError("invalid_client", status=401)
    refresh = _post(request, "refresh_token")
    if not refresh.startswith(REFRESH_PREFIX):
        raise OAuthError("invalid_grant")
    digest = hash_token(refresh)
    with tracking.suppress(), rls_bypass(), transaction.atomic():
        grant = (
            McpGrant.objects.select_for_update()
            .select_related("user", "client")
            .filter(refresh_hash=digest)
            .first()
        )
        if grant is None:
            # Alter Schlüssel noch einmal benutzt: Es gibt eine Kopie, Verbindung beenden
            old = McpGrant.objects.filter(previous_refresh_hash=digest, revoked_at=None).first()
            if old is not None:
                old.revoke("wiederverwendet")
            raise OAuthError("invalid_grant")
        if grant.client_id != client.pk or not grant.is_active:
            raise OAuthError("invalid_grant")
        user = grant.user
        if not user.is_active or user.auth_version != grant.auth_version:
            grant.revoke("konto")
            raise OAuthError("invalid_grant")
        access, new_refresh = grant.issue()
        grant.last_used_at = timezone.now()
        grant.save(
            update_fields=[
                "access_hash",
                "access_expires_at",
                "refresh_hash",
                "previous_refresh_hash",
                "last_used_at",
            ]
        )
    return _answer(grant, access, new_refresh)


def revoke(request) -> None:
    """RFC 7009: Zugriffs- oder Erneuerungsschlüssel; unbekannte Schlüssel sind kein Fehler."""
    value = _post(request, "token")
    if not value.startswith((ACCESS_PREFIX, REFRESH_PREFIX)):
        return
    digest = hash_token(value)
    with tracking.suppress(), rls_bypass():
        field = "access_hash" if value.startswith(ACCESS_PREFIX) else "refresh_hash"
        grant = McpGrant.objects.filter(**{field: digest}, revoked_at=None).first()
        if grant is not None:
            grant.revoke("assistent")
