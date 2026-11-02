"""Anmeldung an der Nextcloud (und ähnlichen Diensten) mit dem HUBIplan-Konto.

HUBIplan ist dafür Anbieter nach OpenID Connect (siehe ``provider``). Jede Einheit trägt
ihre Nextcloud als ``Client`` ein und legt fest, wer sich anmelden darf und welche
Gruppen mitgehen. Codes und Zugriffsschlüssel liegen nur kurz im Cache, nie in der
Datenbank.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from urllib.parse import urlsplit

from django.conf import settings
from django.db import models


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def new_client_id() -> str:
    return "hp-" + secrets.token_urlsafe(18)


def new_salt() -> str:
    return secrets.token_urlsafe(32)


USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._@-]{0,63}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def parse_usernames(text: str) -> list[tuple[str, str, str]]:
    """Zeilen „E-Mail = Benutzername“ → (E-Mail, Name, Fehler). Leer und # wird übersprungen."""
    out: list[tuple[str, str, str]] = []
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        sep = "=" if "=" in line else ":"
        email, _, name = (part.strip() for part in line.partition(sep))
        email, name = email.lower(), name.lower()
        if not EMAIL_RE.match(email):
            out.append((email, name, "email"))
        elif not USERNAME_RE.match(name):
            out.append((email, name, "name"))
        else:
            out.append((email, name, ""))
    return out


# Gruppennamen in der Nextcloud dürfen höchstens 64 Zeichen haben
GROUP_MAX = 64


def clean_groups(value) -> list[str]:
    """Gruppen aus Liste oder Text „A, B“: Leerraum gekürzt, leere und doppelte entfernt."""
    items = value.split(",") if isinstance(value, str) else list(value or [])
    groups = [" ".join(str(g).split()) for g in items]
    return list(dict.fromkeys(g for g in groups if g))


class Client(models.Model):
    class Audience(models.TextChoices):
        BOARD = "board", "Vorstand und Rollen"
        ROLES = "roles", "nur Rollen dieser Einheit"
        MEMBERS = "members", "zusätzlich Mitglieder mit Zugang"

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="oidc_clients"
    )
    name = models.CharField("Name", max_length=100, default="Nextcloud")
    # Adresse der Nextcloud, z. B. https://cloud.example.org (ohne /index.php)
    base_url = models.URLField("Adresse der Nextcloud", max_length=300)
    client_id = models.CharField("Client-ID", max_length=64, unique=True, default=new_client_id)
    # Nur die Prüfsumme; das Geheimnis sieht man einmal beim Anlegen bzw. Erneuern
    secret_hash = models.CharField(max_length=64)
    # Macht die Kennung (sub) je Dienst verschieden: Zwei Dienste können ihre Nutzer
    # nicht über die Kennung zusammenführen.
    subject_salt = models.CharField(max_length=64, default=new_salt)
    audience = models.CharField(
        "Wer darf sich anmelden", max_length=10, choices=Audience.choices, default=Audience.BOARD
    )
    require_mfa = models.BooleanField("nur mit Zwei-Faktor-Anmeldung", default=False)
    # Fachfrage FQ26: Anmeldung nur mit PKCE (S256); user_oidc schickt es von selbst mit
    require_pkce = models.BooleanField("nur mit PKCE (S256)", default=True)
    groups_board = models.BooleanField("Gruppe „Vorstand“", default=True)
    groups_roles = models.BooleanField("je Rolle eine Gruppe", default=True)
    groups_units = models.BooleanField("je Untereinheit eine Gruppe", default=True)
    groups_members = models.BooleanField("Gruppe „Mitglieder“", default=True)
    # Bisherige Benutzernamen in der Nextcloud, je Zeile „E-Mail = Benutzername“. Wer hier
    # steht, wird bei der ersten Anmeldung mit seinem vorhandenen Nextcloud-Konto verbunden
    # (Angabe preferred_username). Bewusst nur von Hand gepflegt: Aus Namen abgeleitet könnte
    # sich jemand durch eine Namensänderung ein fremdes Konto holen.
    usernames = models.TextField("bisherige Benutzernamen", blank=True, default="")
    # Gruppen für Rollen: Rollen-ID → Gruppen, z. B. „1. Kassierer“ und „2. Kassierer“ →
    # „Kassierer“. An der ID statt am Namen, damit Umbenennen nichts ändert. Rollen ohne
    # Eintrag schicken ihren Namen, wenn ``groups_roles`` an ist.
    role_groups = models.JSONField("Gruppen für Rollen", default=dict, blank=True)
    # Konten in der Nextcloud automatisch deaktivieren, wenn der Zugang endet (siehe accounts)
    manage_accounts = models.BooleanField("Konten automatisch deaktivieren", default=False)
    # Dienstkonto in der Nextcloud (Gruppen-Admin der Gruppe ``account_group``) mit App-Passwort
    service_user = models.CharField("Dienstkonto", max_length=64, blank=True, default="")
    # verschlüsselt (accounts.mfa.encrypt), nie in Antworten oder im Protokoll
    service_password = models.TextField(blank=True, default="")
    # Gruppe, die bei jeder Anmeldung mitgeht; das Dienstkonto verwaltet nur ihre Mitglieder
    account_group = models.CharField(
        "Gruppe der Konten über HUBIplan", max_length=64, blank=True, default=""
    )
    # Letzter Fehler oder Halt des Abgleichs (für die Oberfläche)
    sync_error = models.CharField(max_length=500, blank=True, default="")
    synced_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField("eingeschaltet", default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_used_at = models.DateTimeField("zuletzt benutzt", null=True, blank=True)

    # Im Änderungsprotokoll nie Geheimnis oder Salz
    audit_fields = frozenset(
        {
            "name",
            "base_url",
            "client_id",
            "audience",
            "require_mfa",
            "require_pkce",
            "groups_board",
            "groups_roles",
            "groups_units",
            "groups_members",
            "usernames",
            "role_groups",
            "manage_accounts",
            "service_user",
            "account_group",
            "is_active",
        }
    )

    class Meta:
        verbose_name = "Nextcloud-Anmeldung"
        verbose_name_plural = "Nextcloud-Anmeldungen"
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return f"{self.name} ({self.host})"

    @property
    def host(self) -> str:
        return urlsplit(self.base_url).netloc

    def set_secret(self) -> str:
        secret = secrets.token_urlsafe(32)
        self.secret_hash = hash_secret(secret)
        return secret

    def check_secret(self, secret: str) -> bool:
        return bool(self.secret_hash) and secrets.compare_digest(
            self.secret_hash, hash_secret(secret or "")
        )

    def groups_for_role(self, role_id: int) -> list[str]:
        return clean_groups((self.role_groups or {}).get(str(role_id)))

    def username_map(self) -> dict[str, str]:
        """E-Mail (klein) → Benutzername aus ``usernames``; ungültige Zeilen fallen weg."""
        return {email: name for email, name, error in parse_usernames(self.usernames) if not error}

    @property
    def redirect_uris(self) -> list[str]:
        """Rückleitungen der Nextcloud-App „user_oidc“ (mit und ohne index.php)."""
        base = self.base_url.rstrip("/")
        return [f"{base}/apps/user_oidc/code", f"{base}/index.php/apps/user_oidc/code"]


class Account(models.Model):
    """Nextcloud-Konto, das sich über HUBIplan angemeldet hat.

    Nur diese Konten fasst der Abgleich an (deaktivieren und wieder aktivieren); ``admin``
    und Konten ohne Anmeldung über HUBIplan nie.
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="accounts")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    # Benutzername in der Nextcloud: bisheriger Name aus der Liste, sonst die Kennung ``sub``
    nc_user = models.CharField("Benutzername in der Nextcloud", max_length=64)
    first_login_at = models.DateTimeField(auto_now_add=True)
    last_login_at = models.DateTimeField()
    # Nur was HUBIplan selbst deaktiviert hat, aktiviert es wieder
    disabled_by_hubiplan = models.BooleanField(default=False)
    changed_at = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=300, blank=True, default="")

    audit_fields = frozenset({"nc_user", "disabled_by_hubiplan"})

    class Meta:
        verbose_name = "Nextcloud-Konto"
        verbose_name_plural = "Nextcloud-Konten"
        ordering = ["nc_user"]
        constraints = [
            models.UniqueConstraint(fields=["client", "user"], name="oidc_account_unique_user"),
        ]

    def __str__(self) -> str:
        return self.nc_user
