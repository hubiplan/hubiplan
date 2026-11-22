"""API-Zugänge für andere Programme (docs/api.md).

Ein ``ApiAccess`` gehört genau einer Einheit und trägt einzeln gewählte Bereiche. Der
Schlüssel ``hpk_…`` wird einmal gezeigt; in der Datenbank steht nur seine SHA-256-Prüfsumme.

Bereiche mit Personendaten (Stufe 2) gibt es nur mit einem Empfänger aus den Geschäftspartnern
und einer bestätigten Rechtsgrundlage. Jeder Abruf von Personendaten steht im Abrufprotokoll
(``ReadLog``). ``RecordRef`` gibt Datensätzen eine feste, undurchsichtige Kennung nach außen.

Schreiben (Stufe 3): ``WrittenRecord`` hält fest, welchen Datensatz ein Zugang angelegt hat
(nur den darf er ändern) und unter welcher eigenen Kennung des Dritten (``external_id``).
``IdempotencyKey`` merkt sich die Antwort auf eine schreibende Anfrage für 24 Stunden.
"""

from __future__ import annotations

import datetime
import hashlib
import ipaddress
import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy

from core.encfields import EncryptedCharField

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
# Abrufprotokoll und erledigte Benachrichtigungen bleiben so lange
LOG_KEEP = datetime.timedelta(days=90)
# Eine Benachrichtigung wird so lange erneut versucht; danach verfällt sie
HOOK_KEEP = datetime.timedelta(days=3)
# Scheitert jede Zustellung so lange, ruht die Benachrichtigung des Zugangs
HOOK_PAUSE_AFTER = datetime.timedelta(days=7)
HOOK_SECRET_PREFIX = "hpw_"  # noqa: S105 (Kennung, kein Passwort)
# Antworten auf schreibende Anfragen mit ``Idempotency-Key`` bleiben so lange
IDEMPOTENCY_KEEP = datetime.timedelta(hours=24)
MAX_NETWORKS = 20
MAX_PER_UNIT = 50


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def new_hook_secret() -> str:
    return HOOK_SECRET_PREFIX + secrets.token_urlsafe(32)


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
    # Schreibende Anfragen (Stufe 3)
    write_count = models.PositiveBigIntegerField(default=0, db_default=0)
    last_write_at = models.DateTimeField(null=True, blank=True)
    reminded_at = models.DateTimeField(null=True, blank=True)

    # --- Personendaten (Stufe 2): Empfänger und Rechtsgrundlage ---
    class LegalBasis(models.TextChoices):
        NONE = "", gettext_lazy("keine")
        PROCESSING = (
            "processing",
            gettext_lazy("Auftragsverarbeitung (Vertrag nach Art. 28 DSGVO)"),
        )
        TRANSFER = "transfer", gettext_lazy("Übermittlung an einen eigenen Verantwortlichen")

    class ReportLevel(models.TextChoices):
        NUMBERS = "a", gettext_lazy("nur Zahlen")
        NAMES = "b", gettext_lazy("namentlich")

    # Wer die Daten bekommt: ein Geschäftspartner der Einheit
    partner = models.ForeignKey(
        "billing.BusinessPartner",
        verbose_name="Empfänger (Geschäftspartner)",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    legal_basis = models.CharField(
        "Rechtsgrundlage",
        max_length=12,
        choices=LegalBasis.choices,
        blank=True,
        default="",
        db_default="",
    )
    legal_confirmed_at = models.DateTimeField("Rechtsgrundlage bestätigt am", null=True, blank=True)
    legal_confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    third_country = models.BooleanField(
        "Empfänger außerhalb der EU", default=False, db_default=False
    )
    # Zusätzliche Feldgruppen der Mitglieder: contact, membership, units (Stammdaten immer)
    member_fields = models.JSONField("Feldgruppen", default=list, db_default=[], blank=True)
    only_active = models.BooleanField("nur aktuelle Mitglieder", default=True, db_default=True)
    adults_only = models.BooleanField("nur Volljährige", default=False, db_default=False)
    report_level = models.CharField(
        "Verbandsmeldung",
        max_length=1,
        choices=ReportLevel.choices,
        default=ReportLevel.NUMBERS,
        db_default="a",
    )

    # --- Benachrichtigungen (Webhooks) ---
    webhook_url = models.CharField(
        "Adresse für Benachrichtigungen", max_length=500, blank=True, default="", db_default=""
    )
    webhook_secret = EncryptedCharField(max_length=80, blank=True, default="", db_default="")
    webhook_events = models.JSONField("Benachrichtigungen", default=list, db_default=[], blank=True)
    # Seit wann jede Zustellung scheitert (leer: die letzte kam an)
    webhook_failing_since = models.DateTimeField(null=True, blank=True)
    webhook_paused_at = models.DateTimeField(null=True, blank=True)
    webhook_last_ok_at = models.DateTimeField(null=True, blank=True)
    webhook_last_error = models.CharField(max_length=200, blank=True, default="", db_default="")

    audit_fields = frozenset(
        {
            "name",
            "purpose",
            "recipient",
            "scopes",
            "expires_at",
            "allowed_networks",
            "embeddable",
            "partner",
            "legal_basis",
            "legal_confirmed_at",
            "third_country",
            "member_fields",
            "only_active",
            "adults_only",
            "report_level",
            "webhook_url",
            "webhook_events",
        }
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

    @property
    def personal_ok(self) -> bool:
        """Empfänger benannt und Rechtsgrundlage bestätigt: Voraussetzung für Personendaten."""
        return bool(
            self.partner_id
            and self.partner.is_active
            and self.legal_basis
            and self.legal_confirmed_at
        )

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


class RecordRef(models.Model):
    """Feste, undurchsichtige Kennung eines Datensatzes für die API (nie die interne Nummer)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    kind = models.CharField(max_length=20)
    object_id = models.BigIntegerField()
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    class Meta:
        verbose_name = "API-Kennung"
        verbose_name_plural = "API-Kennungen"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "kind", "object_id"], name="partnerapi_ref_unique"
            )
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.public_id}"


class ReadLog(models.Model):
    """Abrufprotokoll: welcher Zugang wann wie viele Datensätze mit Personendaten gelesen hat."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    access = models.ForeignKey(ApiAccess, on_delete=models.CASCADE, related_name="read_logs")
    scope = models.CharField(max_length=40)
    count = models.PositiveIntegerField(default=0)
    at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "API-Abruf"
        verbose_name_plural = "API-Abrufe"
        ordering = ["-at", "-pk"]
        indexes = [models.Index(fields=["access", "-at"])]

    def __str__(self) -> str:
        return f"{self.scope} {self.count}"


class WebhookDelivery(models.Model):
    """Eine Benachrichtigung an die Adresse eines Zugangs: schlank, nur Art und Kennung."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    access = models.ForeignKey(ApiAccess, on_delete=models.CASCADE, related_name="deliveries")
    delivery_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    event = models.CharField(max_length=40)
    object_ref = models.CharField(max_length=40)
    occurred_at = models.DateTimeField(default=timezone.now)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_try_at = models.DateTimeField(default=timezone.now)
    delivered_at = models.DateTimeField(null=True, blank=True)
    dropped_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        verbose_name = "API-Benachrichtigung"
        verbose_name_plural = "API-Benachrichtigungen"
        ordering = ["pk"]
        indexes = [
            models.Index(
                fields=["next_try_at"],
                name="partnerapi_hook_due",
                condition=models.Q(delivered_at__isnull=True, dropped_at__isnull=True),
            )
        ]

    def __str__(self) -> str:
        return f"{self.event} {self.object_ref}"

    @property
    def pending(self) -> bool:
        return self.delivered_at is None and self.dropped_at is None


class WrittenRecord(models.Model):
    """Was ein Zugang angelegt hat. Nur diese Datensätze darf er später ändern; ``external_id``
    ist die eigene Kennung des Dritten, je Zugang und Art eindeutig."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    access = models.ForeignKey(ApiAccess, on_delete=models.CASCADE, related_name="written")
    kind = models.CharField(max_length=20)
    object_id = models.BigIntegerField()
    external_id = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "API-Eintrag"
        verbose_name_plural = "API-Einträge"
        constraints = [
            models.UniqueConstraint(
                fields=["access", "kind", "object_id"], name="partnerapi_written_unique"
            ),
            models.UniqueConstraint(
                fields=["access", "kind", "external_id"],
                condition=~models.Q(external_id=""),
                name="partnerapi_written_external",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.object_id}"


class IdempotencyKey(models.Model):
    """Antwort auf eine schreibende Anfrage: Dieselbe Anfrage mit demselben
    ``Idempotency-Key`` legt nichts doppelt an und bekommt dieselbe Antwort."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    access = models.ForeignKey(ApiAccess, on_delete=models.CASCADE, related_name="+")
    key = models.CharField(max_length=100)
    fingerprint = models.CharField(max_length=64)
    status = models.PositiveSmallIntegerField(default=0)
    body = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "API-Wiederholungsschutz"
        verbose_name_plural = "API-Wiederholungsschutz"
        constraints = [
            models.UniqueConstraint(fields=["access", "key"], name="partnerapi_idempotency_unique")
        ]

    def __str__(self) -> str:
        return f"{self.access_id} {self.created_at:%Y-%m-%d}"
