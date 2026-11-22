"""API-Zugänge für andere Programme (docs/api.md, Stufe 1).

Ein ``ApiAccess`` gehört genau einer Einheit und trägt einzeln gewählte Bereiche. Der
Schlüssel ``hpk_…`` wird einmal gezeigt; in der Datenbank steht nur seine SHA-256-Prüfsumme.
"""

from __future__ import annotations

import datetime
import hashlib
import ipaddress
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

KEY_PREFIX = "hpk_"  # noqa: S105 (Kennung, kein Passwort)

# Ein Zugang gilt höchstens so lange; danach verlängert ihn ein Mensch
MAX_LIFETIME = datetime.timedelta(days=366)
DEFAULT_LIFETIME = datetime.timedelta(days=365)
# Ohne Nutzung ruht der Zugang nach dieser Zeit von selbst
IDLE_LIFETIME = datetime.timedelta(days=90)
# Nach „Neuen Schlüssel erzeugen“ gilt der alte noch so lange (Wechsel ohne Ausfall)
ROTATE_OVERLAP = datetime.timedelta(days=7)
# So früh vor dem Ablauf geht die Erinnerung hinaus
REMIND_BEFORE = datetime.timedelta(days=30)
MAX_NETWORKS = 20
MAX_PER_UNIT = 50


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def parse_networks(values) -> list[str]:
    """Erlaubte Adressen oder Netze in einheitlicher Schreibweise; ``ValueError`` bei Unsinn."""
    out: list[str] = []
    for value in values or []:
        text = str(value).strip()
        if not text:
            continue
        network = ipaddress.ip_network(text, strict=False)
        if str(network) not in out:
            out.append(str(network))
    if len(out) > MAX_NETWORKS:
        raise ValueError("zu viele Netze")
    return out


class ApiAccess(models.Model):
    # Einheit mit eigenem Datenbereich (Verein oder Dachverband)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="api_accesses"
    )
    # Begrenzung auf eine Untereinheit dieses Datenbereichs (leer: die ganze Einheit)
    unit = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="api_accesses_as_unit",
    )
    name = models.CharField("Name", max_length=100)
    purpose = models.CharField("Zweck", max_length=300, blank=True)
    recipient = models.CharField("Empfänger", max_length=200, blank=True)
    scopes = models.JSONField("Bereiche", default=list)
    key_hash = models.CharField(max_length=64, unique=True)
    # Letzte vier Zeichen, damit man den Schlüssel in der Liste wiedererkennt
    key_hint = models.CharField(max_length=8, blank=True)
    key_created_at = models.DateTimeField(default=timezone.now)
    # Vorgänger nach einem Wechsel: gilt bis ``previous_until`` weiter
    previous_key_hash = models.CharField(max_length=64, blank=True, db_index=True)
    previous_until = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField("gültig bis")
    # Leer: von überall; sonst nur aus diesen Netzen
    allowed_networks = models.JSONField("erlaubte Adressen", default=list, blank=True)
    # Für Aufrufe aus dem Browser fremder Webseiten (CORS); nur ohne Mitgliedertermine
    embeddable = models.BooleanField("aus fremden Webseiten aufrufbar", default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Ab hier zählt die Frist ohne Nutzung (Anlegen bzw. „Wieder einschalten“)
    active_since = models.DateTimeField(default=timezone.now)
    last_used_at = models.DateTimeField(null=True, blank=True)
    last_used_ip = models.CharField(max_length=45, blank=True)
    request_count = models.PositiveBigIntegerField(default=0)
    reminded_at = models.DateTimeField(null=True, blank=True)

    audit_fields = frozenset(
        {"name", "purpose", "recipient", "scopes", "expires_at", "allowed_networks", "embeddable"}
    )

    class Meta:
        verbose_name = "API-Zugang"
        verbose_name_plural = "API-Zugänge"
        ordering = ["name", "pk"]

    def __str__(self) -> str:
        return self.name

    @property
    def scope_unit(self):
        """Die Einheit, für die der Zugang spricht."""
        return self.unit if self.unit_id else self.organization

    @property
    def idle_since(self) -> datetime.datetime:
        return max(self.active_since, self.last_used_at or self.active_since)

    @property
    def state(self) -> str:
        now = timezone.now()
        if self.expires_at <= now:
            return "expired"
        if self.idle_since <= now - IDLE_LIFETIME:
            return "idle"
        return "active"

    @property
    def is_active(self) -> bool:
        return self.state == "active"

    def issue(self) -> str:
        """Neuer Schlüssel; der bisherige gilt für die Übergangszeit weiter."""
        key = new_key()
        now = timezone.now()
        if self.key_hash:
            self.previous_key_hash = self.key_hash
            self.previous_until = now + ROTATE_OVERLAP
        self.key_hash = hash_key(key)
        self.key_hint = key[-4:]
        self.key_created_at = now
        return key

    def allows_ip(self, ip: str) -> bool:
        if not self.allowed_networks:
            return True
        try:
            address = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if getattr(address, "ipv4_mapped", None):
            address = address.ipv4_mapped
        for text in self.allowed_networks:
            try:
                network = ipaddress.ip_network(text, strict=False)
            except ValueError:
                continue
            if address.version == network.version and address in network:
                return True
        return False
