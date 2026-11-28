"""Abrechnung: Rechnungseingang (Postfach, eingegangene Rechnungen, Prüfung)."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext, gettext_lazy

from core.encfields import (
    EncryptedCharField,
    EncryptedEmailField,
    EncryptedJSONField,
)
from core.privatefiles import PrivateFileField
from exchange.models import private_storage

from .invoices import electronic_file_path
from .partners import BusinessPartner


class IncomingMailbox(models.Model):
    """Kennung des Vereins in der Plus-Adresse des Rechnungspostfachs (#374).

    Mails an ``rechnung+<tag>@…`` gehören zu diesem Verein. Die Kennung ist zufällig, damit
    niemand die Adresse eines Vereins erraten kann; ``renew`` macht alte Adressen ungültig.
    """

    organization = models.OneToOneField(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    tag = models.CharField(max_length=20, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return gettext("Rechnungspostfach")


class IncomingMail(models.Model):
    """Eine Mail aus dem Rechnungspostfach, die einem Verein zugeordnet ist (#374).

    Übernommene Anhänge verweisen als ``IncomingInvoice.mail`` hierher. Mails ohne
    E-Rechnung erscheinen als Hinweis im Rechnungseingang, bis jemand sie erledigt.
    """

    class Status(models.TextChoices):
        IMPORTED = "imported", gettext_lazy("Übernommen")
        NO_INVOICE = "no_invoice", gettext_lazy("Keine E-Rechnung im Anhang")
        SPAM = "spam", gettext_lazy("Als Spam markiert")
        VIRUS = "virus", gettext_lazy("Schadsoftware gefunden")
        ERROR = "error", gettext_lazy("Nicht verarbeitet")

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    # SHA-256 der Message-ID: Dieselbe Mail wird nur einmal übernommen
    message_hash = models.CharField(max_length=64, blank=True)
    sender = EncryptedEmailField(max_length=254, blank=True, strict=True)
    subject = EncryptedCharField(max_length=300, blank=True, strict=True)
    # Absender passt zur E-Mail-Adresse eines Geschäftspartners
    sender_known = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=Status.choices)
    # Übersprungene Anhänge: [{"name": "brief.pdf", "reason": "plain_pdf"}, …]
    skipped = EncryptedJSONField(default=list, strict=True)
    received_at = models.DateTimeField(auto_now_add=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-received_at", "-pk"]
        indexes = [models.Index(fields=["organization", "message_hash"])]

    def __str__(self):
        return f"Rechnungsmail {self.pk}"


class IncomingInvoice(models.Model):
    """Eingang bleibt auch bei fehlgeschlagener Prüfung im Original erhalten."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    original = PrivateFileField(storage=private_storage, upload_to=electronic_file_path)
    xml = PrivateFileField(storage=private_storage, upload_to=electronic_file_path, blank=True)
    report_xml = PrivateFileField(
        storage=private_storage, upload_to=electronic_file_path, blank=True
    )
    name = EncryptedCharField(max_length=200, strict=True)
    sha256 = models.CharField(max_length=64)
    content_type = models.CharField(max_length=40)
    data = EncryptedJSONField(default=dict, strict=True)
    report = EncryptedJSONField(default=dict, strict=True)
    status = models.CharField(
        max_length=12,
        default="review",
        choices=[
            ("review", gettext_lazy("Zu prüfen")),
            ("approved", gettext_lazy("Freigegeben")),
            ("rejected", gettext_lazy("Abgelehnt")),
        ],
    )
    # Technische Prüfung läuft im Hintergrund (billing/incoming_check.py)
    validation = models.CharField(
        max_length=8,
        default="done",
        db_default="done",
        choices=[
            ("pending", gettext_lazy("Wird geprüft")),
            ("done", gettext_lazy("Geprüft")),
        ],
    )
    review_note = EncryptedCharField(max_length=2000, blank=True, strict=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True)
    booking = models.OneToOneField(
        "finance.Booking",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="incoming_invoice",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    # Aus dem Rechnungspostfach (#374); leer beim Hochladen
    mail = models.ForeignKey(
        IncomingMail, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices"
    )
    # Geschäftspartner (konzepte/geschaeftspartner.md, P3): von Hand zugeordnet;
    # HUBIplan schlägt nur vor (billing/incoming_partner.py)
    partner = models.ForeignKey(
        BusinessPartner,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Geschäftspartner",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "sha256"], name="eingangsrechnung_datei_einmal"
            )
        ]

    def __str__(self):
        return self.name


class IncomingValidation(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    incoming = models.ForeignKey(
        IncomingInvoice, on_delete=models.PROTECT, related_name="previous_checks"
    )
    report = EncryptedJSONField(default=dict, strict=True)
    report_xml = PrivateFileField(
        storage=private_storage, upload_to=electronic_file_path, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Prüfung {self.incoming_id} / {self.pk}"
