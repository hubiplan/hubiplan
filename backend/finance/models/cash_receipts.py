"""Kasse: Quittungen."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy

from core.encfields import EncryptedCharField

from .base import Account, Category
from .bookings import Booking, Receipt


class CashReceipt(models.Model):
    """Quittung mit zwei Unterschriften (Kassierer und Gegenseite), siehe
    konzepte/digitale-quittung.md.

    Entwurf → abgeschlossen (Buchung im Kassenbuch, Belegnummer = Buchungsnummer, PDF als
    Beleg an der Buchung) → ggf. storniert (Gegenbuchung, neues PDF). Abgeschlossene
    Quittungen werden nie geändert oder gelöscht.
    """

    class Direction(models.TextChoices):
        IN = "in", gettext_lazy("Verein erhält Geld")
        OUT = "out", gettext_lazy("Verein zahlt Geld aus")

    class Status(models.TextChoices):
        DRAFT = "draft", gettext_lazy("Entwurf")
        FINAL = "final", gettext_lazy("abgeschlossen")
        CANCELLED = "cancelled", gettext_lazy("storniert")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    direction = models.CharField("Richtung", max_length=3, choices=Direction.choices)
    status = models.CharField("Status", max_length=10, choices=Status.choices, default=Status.DRAFT)
    counterparty_name = EncryptedCharField("Name der Gegenseite", max_length=200, strict=True)
    partner = models.ForeignKey(
        "billing.BusinessPartner",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Geschäftspartner",
    )
    counterparty_address = models.TextField("Anschrift", max_length=500, blank=True)
    membership = models.ForeignKey(
        "members.Membership",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Mitglied",
    )
    email = models.EmailField("E-Mail der Gegenseite", blank=True)
    amount = models.DecimalField("Betrag", max_digits=12, decimal_places=2)
    purpose = models.CharField("Zweck", max_length=200)
    # Umsatzsteuer nur bei Bedarf (Ralf 30.10.: Standard nein)
    vat_rate = models.DecimalField(
        "USt-Satz in %", max_digits=4, decimal_places=1, null=True, blank=True
    )
    account = models.ForeignKey(
        Account, on_delete=models.RESTRICT, related_name="+", verbose_name="Kasse"
    )
    category = models.ForeignKey(
        Category, on_delete=models.RESTRICT, related_name="+", verbose_name="Kategorie"
    )
    project = models.ForeignKey(
        "Project",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Veranstaltung",
    )
    # Barzahlung zu einer Rechnung (Schritt Q5): der Abschluss bucht die Zahlung
    invoice = models.ForeignKey(
        "billing.Invoice",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="cash_receipts",
        verbose_name="Rechnung",
    )
    # Unterschriften: nur die Form (Linienzüge), keine Zeit- oder Druckwerte
    treasurer_signature = models.JSONField("Unterschrift Kassierer", null=True, blank=True)
    treasurer_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    treasurer_name = EncryptedCharField(max_length=200, blank=True, strict=True)
    treasurer_signed_at = models.DateTimeField(null=True, blank=True)
    counterparty_signature = models.JSONField("Unterschrift Gegenseite", null=True, blank=True)
    counterparty_signed_at = models.DateTimeField(null=True, blank=True)
    counterparty_confirmed = models.CharField("bestätigter Text", max_length=500, blank=True)
    # Zahler unterschreibt nicht (nur wenn der Verein Geld erhält), mit Begründung
    no_signature_reason = models.CharField(max_length=300, blank=True)
    source = models.CharField("erfasst über", max_length=60, blank=True)

    booking = models.OneToOneField(
        Booking,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="cash_receipt",
        verbose_name="Buchung",
    )
    payment = models.OneToOneField(
        "billing.Payment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_receipt",
    )
    # Belegnummer beim Abschluss festgehalten (ändert sich auch beim Neunummerieren nicht)
    number = models.CharField("Belegnummer", max_length=30, blank=True)
    receipt_date = models.DateField("Datum", null=True, blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)
    finalized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    document = models.ForeignKey(
        Receipt, on_delete=models.RESTRICT, null=True, blank=True, related_name="+"
    )
    pdf_sha256 = models.CharField(max_length=64, blank=True)

    cancel_booking = models.OneToOneField(
        Booking,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="cash_receipt_cancel",
    )
    cancel_reason = models.CharField("Grund des Stornos", max_length=300, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    cancel_document = models.ForeignKey(
        Receipt, on_delete=models.RESTRICT, null=True, blank=True, related_name="+"
    )
    cancel_sha256 = models.CharField(max_length=64, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Quittung"
        verbose_name_plural = "Quittungen"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="quittung_betrag_positiv"
            ),
        ]
        indexes = [models.Index(fields=["organization", "status"])]

    def __str__(self) -> str:
        return f"Quittung {self.number or '(Entwurf)'}"

    @property
    def receives(self) -> bool:
        """Verein erhält das Geld (sonst zahlt er es aus)."""
        return self.direction == self.Direction.IN
