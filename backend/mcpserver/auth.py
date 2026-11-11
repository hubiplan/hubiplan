"""Zugriffsschlüssel ``hpm_`` prüfen, nur für ``/api/mcp/verein/`` (docs/mcp.md, Stufe 1a).

Bei jeder Anfrage gilt live: Verbindung nicht getrennt und nicht abgelaufen, Konto aktiv und
nicht neu gesichert (Passwort geändert, überall abgemeldet), zweiter Faktor eingerichtet und
das Zusatzrecht „KI-Assistenten verbinden“ in der Einheit noch vorhanden.
"""

from __future__ import annotations

import datetime

from django.utils import timezone

from access.catalog import MCP_CONNECT
from changes import tracking
from core.tenancy import rls_bypass

from .models import ACCESS_PREFIX, McpGrant, hash_token

# „Zuletzt benutzt“ höchstens so oft schreiben
USED_EVERY = datetime.timedelta(minutes=5)


class TokenInvalid(Exception):
    """401 mit ``WWW-Authenticate``: der Assistent meldet sich neu an."""

    def __init__(self, description: str = ""):
        super().__init__(description)
        self.description = description


def bearer(request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return value.strip()


def find_grant(token: str) -> McpGrant:
    if not token.startswith(ACCESS_PREFIX):
        raise TokenInvalid()
    with rls_bypass():
        grant = (
            McpGrant.objects.select_related("user", "organization", "client")
            .filter(access_hash=hash_token(token))
            .first()
        )
    now = timezone.now()
    if grant is None or grant.access_expires_at <= now or not grant.is_active:
        raise TokenInvalid("Zugriffsschlüssel abgelaufen oder getrennt")
    user = grant.user
    if not user.is_active or user.auth_version != grant.auth_version:
        _end(grant, "konto")
        raise TokenInvalid("Konto gesperrt oder neu gesichert")
    from access.modules import module_on
    from access.permissions import permissions_in
    from accounts.mfa_policy import has_mfa

    from .oauth import MODULE

    if not has_mfa(user) or not grant.organization.is_active:
        raise TokenInvalid("Zwei-Faktor-Anmeldung fehlt")
    if not module_on(grant.organization, MODULE):
        raise TokenInvalid("Modul „KI-Assistenten“ ist aus")
    if MCP_CONNECT not in permissions_in(user, grant.organization):
        raise TokenInvalid("Recht „KI-Assistenten verbinden“ fehlt")
    if grant.last_used_at < now - USED_EVERY:
        with tracking.suppress(), rls_bypass():
            McpGrant.objects.filter(pk=grant.pk).update(last_used_at=now)
        grant.last_used_at = now
    return grant


def _end(grant: McpGrant, reason: str) -> None:
    with tracking.suppress(), rls_bypass():
        grant.revoke(reason)
