"""Abrechnung: Rechnungen, Positionen, Zahlungen, Versand und elektronische Originale."""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy

from core.encfields import (
    EncryptedCharField,
    EncryptedEmailField,
    EncryptedJSONField,
    EncryptedTextField,
)
from core.privatefiles import PrivateFileField
from exchange.models import private_storage

from .settings import ZERO, FeeRun


def electronic_file_path(instance, filename):
    return f"erechnungen/{instance.organization_id}/{instance.pk}/{filename}"


class InvoiceArtifact(models.Model):
    """Original und Prüfnachweis einer ausgestellten Rechnung; nur einmal erzeugen."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    invoice = models.OneToOneField(
        "billing.Invoice", on_delete=models.PROTECT, related_name="electronic_artifact"
    )
    xml = PrivateFileField(storage=private_storage, upload_to=electronic_file_path)
    sha256 = models.CharField(max_length=64)
    report = EncryptedJSONField(default=dict, strict=True)
    report_xml = PrivateFileField(storage=private_storage, upload_to=electronic_file_path)
    cancellation_xml = PrivateFileField(
        storage=private_storage, upload_to=electronic_file_path, blank=True
    )
    cancellation_report_xml = PrivateFileField(
        storage=private_storage, upload_to=electronic_file_path, blank=True
    )
    cancellation_report = EncryptedJSONField(default=dict, blank=True, strict=True)
    cancellation_sha256 = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"E-Rechnung {self.invoice_id}"


def invoice_pdf_path(instance, filename: str) -> str:
    return f"rechnungen/{instance.organization_id}/{instance.pk}-{filename}"


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", gettext_lazy("Entwurf")
        OPEN = "open", gettext_lazy("offen")
        PAID = "paid", gettext_lazy("bezahlt")
        SETTLED = "settled", gettext_lazy("Abgerechnet")
        CANCELLED = "cancelled", gettext_lazy("storniert")

    class Recipient(models.TextChoices):
        MEMBER = "member", gettext_lazy("Mitglied")
        DEPARTMENT = "department", gettext_lazy("Abteilung")
        CLUB = "club", gettext_lazy("Verein")
        PARTNER = "partner", gettext_lazy("Geschäftspartner")
        # Nach Ablauf der Aufbewahrungsfrist: ohne Bezug auf eine Person (Audit 02.11. BP-F03)
        ANONYMIZED = "anonymized", gettext_lazy("anonymisiert")
        # Haushalt oder Firma: eine Rechnung an den Zahler (Konzept Familien, H2)
        HOUSEHOLD = "household", gettext_lazy("Haushalt/Firma")
        # Anmeldung zu einem Termin (Gast ohne Mitgliedschaft); Angaben aus der Anmeldung
        REGISTRATION = "registration", gettext_lazy("Teilnehmende")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    # Nummer erst beim Festschreiben; Geschäftsjahr nach Rechnungsdatum
    year = models.PositiveSmallIntegerField("Geschäftsjahr", null=True, blank=True)
    number = models.PositiveIntegerField("Rechnungsnummer", null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    recipient_kind = models.CharField(max_length=12, choices=Recipient.choices)
    partner = models.ForeignKey(
        "billing.BusinessPartner",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoices",
    )
    # Validierter, strukturierter Rechnungsinhalt. Leer bei bisherigen Beitragsrechnungen.
    electronic_data = EncryptedJSONField(default=dict, blank=True, strict=True)
    payment_category = models.ForeignKey(
        "finance.Category", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    membership = models.ForeignKey(
        "members.Membership",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoices",
        verbose_name="Mitglied",
    )
    # Haushalts- bzw. Firmenrechnung (H2); Empfänger ist eingefroren, der Haushalt darf
    # später entfallen (Löschfrist), die Rechnung bleibt
    household = models.ForeignKey(
        "members.Household",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
        verbose_name="Haushalt/Firma",
    )
    department = models.ForeignKey(
        "organizations.Department",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoices",
        verbose_name="Abteilung",
    )
    # Dachverband an Verein
    club = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="received_invoices",
        verbose_name="Verein",
    )
    run = models.ForeignKey(
        FeeRun, on_delete=models.CASCADE, null=True, blank=True, related_name="invoices"
    )
    # Veranstaltung (Finanzen); Zahlungen werden ihr in der Kasse zugeordnet
    project = models.ForeignKey(
        "finance.Project",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoices",
        verbose_name="Veranstaltung",
    )
    # Anschrift und E-Mail, wie sie beim Festschreiben galten
    recipient_name = EncryptedCharField("Empfänger", max_length=200, strict=True)
    recipient_address = EncryptedTextField("Anschrift", blank=True)
    recipient_email = EncryptedEmailField("E-Mail", blank=True)
    # Angaben des Rechnungsempfängers, die auf die Rechnung gedruckt werden (J3)
    order_reference = models.CharField(
        "Bestellnummer", max_length=100, blank=True, default="", db_default=""
    )
    leitweg_id = models.CharField(
        "Leitweg-ID", max_length=50, blank=True, default="", db_default=""
    )
    date = models.DateField("Rechnungsdatum")
    due_date = models.DateField("fällig am")
    subject = models.CharField("Betreff", max_length=200, default="Rechnung")
    note = models.TextField("Hinweis", blank=True)
    total = models.DecimalField("Betrag", max_digits=12, decimal_places=2, default=ZERO)
    document_kind = models.CharField(
        max_length=10,
        default="invoice",
        db_default="invoice",
        choices=[("invoice", "invoice"), ("advance", "advance"), ("final", "final")],
    )
    prepaid = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO, db_default=ZERO)
    paid = models.DecimalField("bezahlt", max_digits=12, decimal_places=2, default=ZERO)
    sent_at = models.DateTimeField("per E-Mail verschickt", null=True, blank=True)
    # Die Rechnung, wie sie ausgegeben wurde (Fachfrage 4, Audit 31.10.): spätere Änderungen
    # an Briefkopf oder Bankverbindung ändern sie nicht mehr
    issued_pdf = PrivateFileField(
        "ausgegebene Rechnung", storage=private_storage, upload_to=invoice_pdf_path, blank=True
    )
    issued_pdf_sha256 = models.CharField(max_length=64, blank=True)
    cancelled_at = models.DateTimeField("storniert am", null=True, blank=True)
    # Stornorechnung (konzepte/bankanbindung-stornorechnung.md, Teil A): eigener Beleg mit
    # Nummer „<Rechnungsnummer>-S“, Datum und Grund, einmal abgelegt
    cancel_reason = models.CharField(
        "Grund des Stornos", max_length=300, blank=True, default="", db_default=""
    )
    cancellation_date = models.DateField("Datum der Stornorechnung", null=True, blank=True)
    cancellation_pdf = PrivateFileField(
        "Stornorechnung",
        storage=private_storage,
        upload_to=invoice_pdf_path,
        blank=True,
        db_default="",
    )
    cancellation_pdf_sha256 = models.CharField(max_length=64, blank=True, default="", db_default="")
    cancellation_sent_at = models.DateTimeField("Stornorechnung verschickt", null=True, blank=True)
    dunning_level = models.PositiveSmallIntegerField("Mahnstufe", default=0)
    dunned_at = models.DateField("zuletzt gemahnt am", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Rechnung"
        verbose_name_plural = "Rechnungen"
        ordering = ["-date", "-number", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "year", "number"], name="rechnungsnummer_eindeutig"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(recipient_kind="member", membership__isnull=False)
                    | models.Q(recipient_kind="department", department__isnull=False)
                    | models.Q(recipient_kind="club", club__isnull=False)
                    | models.Q(recipient_kind="partner", partner__isnull=False)
                    | models.Q(recipient_kind="anonymized", membership__isnull=True)
                    | models.Q(recipient_kind="household", membership__isnull=True)
                    | models.Q(recipient_kind="registration", membership__isnull=True)
                ),
                name="rechnung_empfaenger",
            ),
        ]
        indexes = [models.Index(fields=["organization", "status"])]

    def __str__(self) -> str:
        return f"{self.display_number} {self.recipient_name}"

    @property
    def display_number(self) -> str:
        if self.number is None:
            return "Entwurf"
        return f"R{self.organization.fiscal_label(self.year)}-{self.number:04d}"

    @property
    def cancellation_number(self) -> str:
        """Nummer der Stornorechnung (Fachfrage F-1: Rechnungsnummer plus „-S“)."""
        return f"{self.display_number}-S" if self.number is not None else ""

    @property
    def outstanding(self) -> Decimal:
        if self.status in (self.Status.DRAFT, self.Status.CANCELLED, self.Status.SETTLED):
            return ZERO
        return max(self.total - self.paid - self.prepaid, ZERO)


class InvoiceAdvance(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    final_invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="advance_allocations"
    )
    advance = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="final_allocations")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    snapshot = EncryptedJSONField(default=dict, strict=True)
    active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["advance"],
                condition=models.Q(active=True),
                name="invoice_advance_one_active_final",
            )
        ]

    def __str__(self):
        return f"Anzahlungszuordnung {self.pk}"


def hybrid_file_path(instance, filename):
    return f"erechnungen/{instance.organization_id}/hybrid/{instance.pk}/{filename}"


class InvoiceHybridArtifact(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="hybrid_artifacts")
    document = models.CharField(max_length=12, default="invoice")
    pdf = PrivateFileField(storage=private_storage, upload_to=hybrid_file_path)
    xml = PrivateFileField(storage=private_storage, upload_to=hybrid_file_path)
    cii_report = PrivateFileField(storage=private_storage, upload_to=hybrid_file_path)
    pdf_report = PrivateFileField(storage=private_storage, upload_to=hybrid_file_path)
    sha256 = models.CharField(max_length=64)
    xml_sha256 = models.CharField(max_length=64)
    source_sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "document"], name="invoice_hybrid_document_once"
            )
        ]

    def __str__(self):
        return f"Hybridrechnung {self.invoice_id}"


class InvoiceDelivery(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="deliveries")
    document = models.CharField(
        max_length=12, choices=[("invoice", "invoice"), ("cancellation", "cancellation")]
    )
    # Preserved in data transfers as external delivery evidence. The request ID may
    # consequently also exist in an imported organisation's historical records.
    request_id = models.UUIDField(default=uuid.uuid4)
    provider_signature = models.CharField(max_length=64)
    provider_label = models.CharField(max_length=100)
    sha256 = models.CharField(max_length=64)
    status = models.CharField(max_length=15, default="prepared")
    receipt = EncryptedJSONField(default=dict, strict=True)
    error_code = models.CharField(max_length=30, blank=True)
    attempted_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "document", "provider_signature"],
                name="invoice_delivery_provider_document",
            )
        ]

    def __str__(self):
        return f"Rechnungsversand {self.pk}"


class InvoiceLine(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField(default=0)
    text = EncryptedCharField("Text", max_length=200, strict=True)
    detail = EncryptedCharField("Zusatz", max_length=200, blank=True, strict=True)
    amount = models.DecimalField("Betrag", max_digits=10, decimal_places=2)
    # Netto, Menge, Einheit und Steuerkategorie für Leistungsrechnungen; der bestehende
    # Bruttobetrag bleibt für Kasse und alte Clients erhalten.
    electronic_data = EncryptedJSONField(default=dict, blank=True, strict=True)
    # Beitragsposten: für welches Mitglied (auch in Sammelrechnungen)
    membership = models.ForeignKey(
        "members.Membership",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    is_fee = models.BooleanField("Beitrag aus Beitragslauf", default=False)
    is_dunning_fee = models.BooleanField("Mahngebühr", default=False)
    # Umsatzsteuer im Bruttobetrag enthalten (None/0 = keine)
    vat_rate = models.DecimalField(
        "Steuersatz", max_digits=4, decimal_places=2, null=True, blank=True
    )

    class Meta:
        verbose_name = "Rechnungsposten"
        verbose_name_plural = "Rechnungsposten"
        ordering = ["position", "pk"]

    def __str__(self) -> str:
        return self.text


class Payment(models.Model):
    class Method(models.TextChoices):
        TRANSFER = "transfer", gettext_lazy("Überweisung")
        CASH = "cash", gettext_lazy("bar")
        DEBIT = "debit", gettext_lazy("Lastschrift")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    date = models.DateField("Datum")
    amount = models.DecimalField("Betrag", max_digits=12, decimal_places=2)
    method = models.CharField("Zahlungsweg", max_length=10, choices=Method.choices)
    booking = models.OneToOneField(
        "finance.Booking",
        on_delete=models.PROTECT,
        related_name="payment",
        verbose_name="Buchung",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Zahlung"
        verbose_name_plural = "Zahlungen"
        ordering = ["date", "pk"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="zahlung_positiv")
        ]

    def __str__(self) -> str:
        return f"{self.amount} am {self.date}"
