"""Online-Mitgliedsanträge (Konzept konzepte/online-beitrittsformular.md, Stufen B1–B5).

Ein Antrag ist eine Zwischenstufe: Er legt weder Person noch Mitgliedschaft noch Mandat an.
Erst die Annahme durch den Verein ruft ``members.services.admit`` auf und legt Mandat und
Einwilligungen an. Personendaten, Bankdaten, Erziehungsberechtigte und Unterschrift liegen
verschlüsselt mit dem Schlüssel des Vereins (core/encfields.py).
"""

from __future__ import annotations

import hashlib

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy

from core.encfields import EncryptedJSONField

PURGE_MONTHS = 6
UNCONFIRMED_HOURS = 48


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def default_fields() -> dict:
    return {
        "phone": "optional",
        "gender": "optional",
        "birth_date": "optional",
        "unit": "off",
        "entry_wish": "off",
        "note": "optional",
    }


def default_rule() -> dict:
    return {
        "mode": "single",
        "roles": [],
        "min_count": 0,
        "pool": [],
        "unit": False,
        "auto_admit": False,
        "multi_role": False,
    }


class ApplicationForm(models.Model):
    """Einstellungen des Online-Antrags eines Vereins (höchstens einer je Verein)."""

    class Sepa(models.TextChoices):
        OFF = "off", gettext_lazy("nicht anbieten")
        OFFER = "offer", gettext_lazy("anbieten")
        REQUIRED = "required", gettext_lazy("Pflicht")

    class Signature(models.TextChoices):
        NONE = "none", gettext_lazy("Bestätigung per E-Mail genügt")
        REQUIRED = "required", gettext_lazy("Unterschrift nötig")

    class EntryDate(models.TextChoices):
        DECISION = "decision", gettext_lazy("Tag der Annahme")
        NEXT_MONTH = "next_month", gettext_lazy("Erster des Folgemonats")
        WISH = "wish", gettext_lazy("Wunschdatum aus dem Antrag")

    organization = models.OneToOneField(
        "organizations.Organization", on_delete=models.CASCADE, related_name="application_form"
    )
    enabled = models.BooleanField("Online-Antrag an", default=False)
    # Öffentliche Kennung der Formularadresse (bleibt beim Aus- und Einschalten gleich)
    public_key = models.CharField(max_length=40, unique=True)
    # Wählbare Mitgliedsarten: [{"id", "label": {"de", "en"}, "text": {"de", "en"},
    # "organizations": bool}] in dieser Reihenfolge
    types = models.JSONField("Wählbare Mitgliedsarten", default=list, blank=True)
    # Feld → "required" | "optional" | "off"
    fields = models.JSONField("Felder", default=default_fields, blank=True)
    # Zusatzfelder (customfields.FieldDefinition), die im Antrag abgefragt werden (B5)
    custom_fields = models.JSONField("Zusatzfelder", default=list, blank=True)
    sepa = models.CharField("Lastschrift", max_length=10, choices=Sepa.choices, default="offer")
    confirm_statute = models.BooleanField("Satzung bestätigen", default=True)
    confirm_fee_rules = models.BooleanField("Beitragsordnung bestätigen", default=True)
    # Freiwillige Einwilligungen: "club_photo" (Vereinsfotos) und Kategorien aus
    # website.PublicationConsent
    consents = models.JSONField("Freiwillige Einwilligungen", default=list, blank=True)
    signature = models.CharField(
        "Unterschrift", max_length=10, choices=Signature.choices, default="none"
    )
    # Texte je Sprache: {"intro": {"de", "en"}, "thanks", "welcome", "rejection"}
    texts = models.JSONField("Texte", default=dict, blank=True)
    # Rollen (access.Role), die eine Hinweismail zu neuen Anträgen bekommen; leer = alle
    # Rollen mit Recht „Mitglieder bearbeiten“
    notify_roles = models.JSONField("Hinweis an Rollen", default=list, blank=True)
    # Zustimmungen nach Satzung (admission/rules.py)
    rule = models.JSONField("Zustimmungen", default=default_rule, blank=True)
    entry_date = models.CharField(
        "Eintrittsdatum", max_length=12, choices=EntryDate.choices, default="decision"
    )
    purge_months = models.PositiveSmallIntegerField(
        "Löschfrist abgelehnter Anträge (Monate)", default=PURGE_MONTHS
    )
    # Minderjährige (B3): leer = keine Altersgrenze; Erziehungsberechtigte unter 18 Pflicht
    min_age = models.PositiveSmallIntegerField("Mindestalter", null=True, blank=True)
    minors = models.BooleanField("Minderjährige dürfen beantragen", default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Einstellungen des Online-Antrags"
        verbose_name_plural = "Einstellungen des Online-Antrags"

    def __str__(self) -> str:
        return f"Online-Antrag {self.organization}"


class Application(models.Model):
    class Status(models.TextChoices):
        UNCONFIRMED = "unconfirmed", gettext_lazy("E-Mail noch nicht bestätigt")
        UNSIGNED = "unsigned", gettext_lazy("wartet auf Unterschrift")
        OPEN = "open", gettext_lazy("eingegangen")
        QUERY = "query", gettext_lazy("Rückfrage")
        ACCEPTED = "accepted", gettext_lazy("angenommen")
        REJECTED = "rejected", gettext_lazy("abgelehnt")
        WITHDRAWN = "withdrawn", gettext_lazy("zurückgezogen")

    class Source(models.TextChoices):
        WEB = "web", gettext_lazy("Webseite")
        KIOSK = "kiosk", gettext_lazy("Stand")

    OPEN_STATES = ("unsigned", "open", "query")
    DONE_STATES = ("accepted", "rejected", "withdrawn")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default="unconfirmed")
    source = models.CharField(max_length=8, choices=Source.choices, default="web")
    language = models.CharField(max_length=5, default="de")
    kind = models.CharField(max_length=12, default="person")  # person | organization
    # Angaben: Name, Vorname, Anschrift, Kontakt, Geburtsdatum, Zusatzfelder, Bemerkung …
    data = EncryptedJSONField("Angaben", default=dict, blank=True, strict=True)
    member_type = models.ForeignKey(
        "members.MemberType", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    unit = models.ForeignKey(
        "organizations.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    entry_wish = models.DateField("Wunsch-Eintritt", null=True, blank=True)
    # Lastschrift: {"holder", "iban", "bic", "text"}; nach Annahme geleert (liegt dann im Mandat)
    mandate = EncryptedJSONField("Mandat", default=dict, blank=True, strict=True)
    # Bestätigungen und Einwilligungen: [{"key", "label", "text", "version", "at"}]
    consents = models.JSONField("Einwilligungen", default=list, blank=True)
    # Erziehungsberechtigte (B3): [{"last_name", "first_name", "email", "phone"}]
    guardians = EncryptedJSONField("Erziehungsberechtigte", default=list, blank=True, strict=True)
    # Unterschrift (finance/signature.py, nur Linienzüge) und wer unterschrieben hat
    signature = EncryptedJSONField("Unterschrift", default=dict, blank=True, strict=True)
    signed_at = models.DateTimeField("unterschrieben am", null=True, blank=True)
    token_hash = models.CharField(max_length=64, unique=True)
    confirmed_at = models.DateTimeField("E-Mail bestätigt am", null=True, blank=True)
    decided_at = models.DateTimeField("entschieden am", null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    decision_note = models.CharField("Vermerk", max_length=500, blank=True)
    membership = models.ForeignKey(
        "members.Membership",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="applications",
    )
    purge_after = models.DateField("löschen ab", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Mitgliedsantrag"
        verbose_name_plural = "Mitgliedsanträge"
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["organization", "status"])]

    def __str__(self) -> str:
        return f"Antrag {self.number}"

    @property
    def number(self) -> str:
        return f"A{self.created_at:%Y}-{self.pk:05d}" if self.created_at and self.pk else ""

    @property
    def display_name(self) -> str:
        d = self.data or {}
        if self.kind == "organization":
            return d.get("last_name", "")
        return " ".join(p for p in (d.get("first_name", ""), d.get("last_name", "")) if p)

    @property
    def email(self) -> str:
        return (self.data or {}).get("email", "")

    @property
    def is_open(self) -> bool:
        return self.status in self.OPEN_STATES


class Approval(models.Model):
    """Zustimmung oder Ablehnung einer Person nach der Regel des Vereins."""

    class Decision(models.TextChoices):
        APPROVE = "approve", gettext_lazy("stimmt zu")
        REJECT = "reject", gettext_lazy("lehnt ab")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="approvals")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    user_name = models.CharField("Name", max_length=200)
    # Rollen (access.Role) der Person zum Zeitpunkt der Zustimmung
    role_ids = models.JSONField(default=list, blank=True)
    role_names = models.CharField("Rollen", max_length=300, blank=True)
    # Zustimmung für die gewünschte Untereinheit (vom Vorstand vermerkt)
    for_unit = models.BooleanField(default=False)
    decision = models.CharField(max_length=8, choices=Decision.choices)
    note = models.CharField("Vermerk", max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Zustimmung"
        verbose_name_plural = "Zustimmungen"
        ordering = ["created_at", "pk"]

    def __str__(self) -> str:
        return f"Zustimmung {self.user_name}"


class ApplicationEvent(models.Model):
    """Verlauf eines Antrags (ohne Personendaten)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=20)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self) -> str:
        return self.kind


class KioskLink(models.Model):
    """Stand-Modus (B5): ein Gerät nimmt Anträge ohne E-Mail-Bestätigung auf."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    label = models.CharField("Bezeichnung", max_length=100)
    token_hash = models.CharField(max_length=64, unique=True)
    valid_until = models.DateTimeField("gültig bis")
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Stand-Link"
        verbose_name_plural = "Stand-Links"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Stand-Link {self.label}"
