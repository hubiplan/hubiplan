"""KI-Assistenten mit Anmeldung (Stufe 1a, docs/mcp.md).

``McpClient``: ein KI-Assistent, der sich selbst angemeldet hat (OAuth Dynamic Client
Registration, RFC 7591). Er bekommt nur eine Kennung, kein Geheimnis; die Anmeldung
schützt PKCE (S256) und die feste Rückleitung.

``McpGrant``: die Zustimmung einer Person für genau eine Einheit und bestimmte Bereiche.
Zugriffs- und Erneuerungsschlüssel stehen nur als Prüfsumme in der Datenbank.
"""

from __future__ import annotations

import datetime
import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

ACCESS_PREFIX = "hpm_"  # noqa: S105 (Kennung, kein Passwort)
REFRESH_PREFIX = "hpmr_"  # noqa: S105
CLIENT_PREFIX = "hpmc_"

ACCESS_LIFETIME = datetime.timedelta(hours=1)
# Höchstens 30 Tage ab der Zustimmung, verfällt nach 14 Tagen ohne Nutzung (Konzept 1a)
GRANT_LIFETIME = datetime.timedelta(days=30)
IDLE_LIFETIME = datetime.timedelta(days=14)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_client_id() -> str:
    return CLIENT_PREFIX + secrets.token_urlsafe(18)


class McpClient(models.Model):
    client_id = models.CharField(max_length=64, unique=True, default=new_client_id)
    name = models.CharField("Name", max_length=100)
    redirect_uris = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "KI-Assistent"
        verbose_name_plural = "KI-Assistenten"

    def __str__(self) -> str:
        return self.name


class McpGrant(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mcp_grants"
    )
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="mcp_grants"
    )
    client = models.ForeignKey(McpClient, on_delete=models.CASCADE, related_name="grants")
    scopes = models.JSONField(default=list)
    access_hash = models.CharField(max_length=64, unique=True)
    access_expires_at = models.DateTimeField()
    refresh_hash = models.CharField(max_length=64, unique=True)
    # Vorgänger nach dem Erneuern: Wer ihn noch einmal benutzt, hat eine Kopie (Grant endet)
    previous_refresh_hash = models.CharField(max_length=64, blank=True, db_index=True)
    auth_version = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    last_used_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=40, blank=True)

    class Meta:
        verbose_name = "Verbindung eines KI-Assistenten"
        verbose_name_plural = "Verbindungen von KI-Assistenten"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.client} → {self.organization}"

    @property
    def is_active(self) -> bool:
        now = timezone.now()
        return (
            self.revoked_at is None
            and self.expires_at > now
            and self.last_used_at > now - IDLE_LIFETIME
        )

    def issue(self) -> tuple[str, str]:
        """Neue Schlüssel (Zugriff und Erneuerung); gespeichert wird nur die Prüfsumme."""
        access = ACCESS_PREFIX + secrets.token_urlsafe(32)
        refresh = REFRESH_PREFIX + secrets.token_urlsafe(32)
        if self.refresh_hash:
            self.previous_refresh_hash = self.refresh_hash
        self.access_hash = hash_token(access)
        self.refresh_hash = hash_token(refresh)
        self.access_expires_at = timezone.now() + ACCESS_LIFETIME
        return access, refresh

    def revoke(self, reason: str) -> None:
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.revoked_reason = reason[:40]
            self.save(update_fields=["revoked_at", "revoked_reason"])
