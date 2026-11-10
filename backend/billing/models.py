"""Beiträge und Rechnungen.

- ``BillingSettings``: Rhythmus, Zahlungsziel, Konto und Kategorie für Zahlungen.
- ``FeeRate`` und ``AgeRate``: Beitrag je Mitgliedsart, Altersstufen mit eigenem
  Betrag oder Abschlag. Beträge gelten für ein ganzes Beitragsjahr (= Geschäftsjahr).
- ``FeeRun``: ein Beitragslauf für einen Abrechnungszeitraum.
- ``Invoice`` mit ``InvoiceLine``: Rechnung an ein Mitglied oder als
  Sammelrechnung an eine Abteilung.
- ``Payment``: Zahlungseingang, erzeugt eine Einnahme-Buchung in der Kasse.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext, gettext_lazy

from core.encfields import (
    EncryptedCharField,
    EncryptedEmailField,
    EncryptedJSONField,
    EncryptedTextField,
)
from core.privatefiles import PrivateFileField
from exchange.models import private_storage

ZERO = Decimal("0.00")


class BusinessPartner(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    name = EncryptedCharField(max_length=200, strict=True)
    is_customer = models.BooleanField(default=True)
    is_supplier = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    # Ein Schema für Kunden, Lieferanten und die eingefrorenen Rechnungsanschriften.
    details = EncryptedJSONField(default=dict, strict=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return self.name


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


class Rhythm(models.TextChoices):
    YEARLY = "yearly", gettext_lazy("jährlich")
    HALFYEARLY = "halfyearly", gettext_lazy("halbjährlich")
    QUARTERLY = "quarterly", gettext_lazy("vierteljährlich")
    MONTHLY = "monthly", gettext_lazy("monatlich")


PERIODS_PER_YEAR = {
    Rhythm.YEARLY: 1,
    Rhythm.HALFYEARLY: 2,
    Rhythm.QUARTERLY: 4,
    Rhythm.MONTHLY: 12,
}


class BillingSettings(models.Model):
    organization = models.OneToOneField(
        "organizations.Organization", on_delete=models.CASCADE, related_name="billing_settings"
    )
    rhythm = models.CharField(
        "Abrechnungsrhythmus", max_length=12, choices=Rhythm.choices, default=Rhythm.YEARLY
    )
    due_days = models.PositiveSmallIntegerField("Zahlungsziel in Tagen", default=14)
    pro_rata = models.BooleanField(
        "Eintritt im laufenden Zeitraum anteilig berechnen (je angefangenem Monat)",
        default=False,
    )
    account = models.ForeignKey(
        "finance.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Konto für Überweisungen",
    )
    category = models.ForeignKey(
        "finance.Category",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Kategorie für Beitragszahlungen",
    )
    intro_text = models.TextField(
        "Text vor den Posten",
        blank=True,
        default="wir berechnen Ihnen den Mitgliedsbeitrag wie folgt:",
    )
    footer_text = models.TextField("Text unter der Rechnung", blank=True)
    qr_code = models.BooleanField("QR-Code für die Banking-App aufdrucken", default=True)
    # Umsatzsteuer (Standard: nicht ausgewiesen)
    vat_enabled = models.BooleanField("Umsatzsteuer auf Rechnungen ausweisen", default=False)
    vat_rate = models.DecimalField(
        "Steuersatz in Prozent", max_digits=4, decimal_places=2, default=Decimal("19.00")
    )
    tax_number = models.CharField("Steuernummer oder USt-IdNr.", max_length=50, blank=True)
    # Dachverband: Beitrag der Vereine je gemeldetem Mitglied (Jahresbeträge)
    club_rate_active = models.DecimalField(
        "je gemeldetem aktiven Mitglied", max_digits=10, decimal_places=2, null=True, blank=True
    )
    club_rate_passive = models.DecimalField(
        "je gemeldetem passiven Mitglied", max_digits=10, decimal_places=2, null=True, blank=True
    )
    club_base_amount = models.DecimalField(
        "Grundbetrag je Verein", max_digits=10, decimal_places=2, null=True, blank=True
    )
    # SEPA-Lastschrift; ausgeschaltet verschwinden Lastschriften und Mandate aus der Oberfläche
    sepa_enabled = models.BooleanField("SEPA-Lastschrift nutzen", default=False)
    creditor_id = models.CharField("Gläubiger-Identifikationsnummer", max_length=35, blank=True)
    prenotification_days = models.PositiveSmallIntegerField(
        "Vorabankündigung (Tage vor dem Einzug)", default=14
    )
    # E-Rechnung (XRechnung) für Beitragsrechnungen an Mitglieder mit Leitweg-ID (J8a)
    einvoice_members = models.BooleanField(
        "Rechnungen an Mitglieder mit Leitweg-ID als E-Rechnung (XRechnung)",
        default=False,
        db_default=False,
    )
    einvoice_contact = models.CharField(
        "Ansprechpartner für Rechnungsfragen", max_length=100, blank=True, default="", db_default=""
    )
    einvoice_phone = models.CharField(
        "Telefon für Rechnungsfragen", max_length=50, blank=True, default="", db_default=""
    )
    einvoice_email = models.EmailField(
        "E-Mail für Rechnungsfragen", blank=True, default="", db_default=""
    )
    einvoice_identifier = models.CharField(
        "Kennung des Rechnungsstellers",
        max_length=100,
        blank=True,
        default="",
        db_default="",
        help_text="z. B. Vereinsregisternummer; leer: aus dem Impressum",
    )

    class Meta:
        verbose_name = "Beitragseinstellungen"
        verbose_name_plural = "Beitragseinstellungen"

    def __str__(self) -> str:
        return f"Beitragseinstellungen {self.organization}"

    @property
    def periods(self) -> int:
        return PERIODS_PER_YEAR[self.rhythm]


class FeeRate(models.Model):
    """Jahresbeitrag je Mitgliedsart."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    member_type = models.OneToOneField(
        "members.MemberType", on_delete=models.CASCADE, related_name="fee_rate"
    )
    amount = models.DecimalField("Jahresbeitrag", max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "Beitragssatz"
        verbose_name_plural = "Beitragssätze"

    def __str__(self) -> str:
        return f"{self.member_type}: {self.amount}"

    def clean(self):
        if self.amount is not None and self.amount < 0:
            raise ValidationError({"amount": gettext("Der Beitrag darf nicht negativ sein.")})


class AgeRate(models.Model):
    """Altersstufe: eigener Jahresbeitrag oder Abschlag in Prozent.

    Maßgeblich ist das Alter zu Beginn des Beitragsjahres. Ohne Mitgliedsart gilt
    die Stufe für alle Mitgliedsarten; eine Stufe mit Mitgliedsart geht vor.
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    name = models.CharField("Bezeichnung", max_length=100)
    member_type = models.ForeignKey(
        "members.MemberType",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="nur für Mitgliedsart",
    )
    min_age = models.PositiveSmallIntegerField("ab Alter", null=True, blank=True)
    max_age = models.PositiveSmallIntegerField("bis Alter (einschließlich)", null=True, blank=True)
    amount = models.DecimalField(
        "eigener Jahresbeitrag", max_digits=10, decimal_places=2, null=True, blank=True
    )
    discount_percent = models.DecimalField(
        "Abschlag in Prozent", max_digits=5, decimal_places=2, null=True, blank=True
    )

    class Meta:
        verbose_name = "Altersstufe"
        verbose_name_plural = "Altersstufen"
        ordering = ["min_age", "max_age", "name"]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        errors = {}
        if self.min_age is None and self.max_age is None:
            errors["max_age"] = gettext("Bitte ein Mindest- oder Höchstalter angeben.")
        if self.min_age is not None and self.max_age is not None and self.min_age > self.max_age:
            errors["max_age"] = gettext("Das Höchstalter liegt unter dem Mindestalter.")
        if (self.amount is None) == (self.discount_percent is None):
            errors["amount"] = gettext(
                "Bitte entweder einen eigenen Beitrag oder einen Abschlag angeben."
            )
        if self.amount is not None and self.amount < 0:
            errors["amount"] = gettext("Der Beitrag darf nicht negativ sein.")
        if self.discount_percent is not None and not (0 < self.discount_percent <= 100):
            errors["discount_percent"] = gettext("Der Abschlag liegt zwischen 0 und 100 Prozent.")
        if errors:
            raise ValidationError(errors)

    def matches(self, age: int) -> bool:
        if self.min_age is not None and age < self.min_age:
            return False
        return not (self.max_age is not None and age > self.max_age)


class SizeRate(models.Model):
    """Staffel nach Größe für Organisationsmitglieder (Mitarbeiter, Einwohner …, J8c).

    Eigener Jahresbeitrag ab einer Größe. Ohne Mitgliedsart gilt die Stufe für alle
    Mitgliedsarten; eine Stufe mit Mitgliedsart geht vor. Organisationen ohne Größe
    zahlen den Beitrag der Mitgliedsart.
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    name = models.CharField("Bezeichnung", max_length=100)
    member_type = models.ForeignKey(
        "members.MemberType",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="nur für Mitgliedsart",
    )
    min_size = models.PositiveIntegerField("ab Größe", null=True, blank=True)
    max_size = models.PositiveIntegerField("bis Größe (einschließlich)", null=True, blank=True)
    amount = models.DecimalField("Jahresbeitrag", max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "Größenstufe"
        verbose_name_plural = "Größenstufen"
        ordering = ["min_size", "max_size", "name"]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        errors = {}
        if self.min_size is None and self.max_size is None:
            errors["max_size"] = gettext("Bitte eine Mindest- oder Höchstgröße angeben.")
        if (
            self.min_size is not None
            and self.max_size is not None
            and self.min_size > self.max_size
        ):
            errors["max_size"] = gettext("Die Höchstgröße liegt unter der Mindestgröße.")
        if self.amount is not None and self.amount < 0:
            errors["amount"] = gettext("Der Beitrag darf nicht negativ sein.")
        if errors:
            raise ValidationError(errors)

    def matches(self, size: int) -> bool:
        if self.min_size is not None and size < self.min_size:
            return False
        return not (self.max_size is not None and size > self.max_size)


class FeeRun(models.Model):
    """Beitragslauf für einen Abrechnungszeitraum eines Geschäftsjahres."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    year = models.PositiveSmallIntegerField("Geschäftsjahr")
    rhythm = models.CharField("Rhythmus", max_length=12, choices=Rhythm.choices)
    period = models.PositiveSmallIntegerField("Zeitraum", default=1)
    start_date = models.DateField("von")
    end_date = models.DateField("bis")
    label = models.CharField("Bezeichnung", max_length=100)
    invoice_date = models.DateField("Rechnungsdatum")
    due_date = models.DateField("fällig am")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Kasse bestätigt, dass die Rechnungen ohne E-Mail per Post raus sind (UI-Audit NAF-06)
    post_done_at = models.DateField("Postversand erledigt am", null=True, blank=True)

    class Meta:
        verbose_name = "Beitragslauf"
        verbose_name_plural = "Beitragsläufe"
        ordering = ["-start_date", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "start_date", "end_date"], name="beitragslauf_einmal"
            )
        ]

    def __str__(self) -> str:
        return self.label


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
        "Stornorechnung", storage=private_storage, upload_to=invoice_pdf_path, blank=True
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


class DunningLevel(models.Model):
    """Mahnstufe: so viele Tage nach Fälligkeit, optional mit Gebühr."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    level = models.PositiveSmallIntegerField("Stufe")
    name = models.CharField("Bezeichnung", max_length=100)
    days = models.PositiveSmallIntegerField("Tage nach Fälligkeit")
    fee = models.DecimalField("Mahngebühr", max_digits=8, decimal_places=2, default=ZERO)
    text = models.TextField("Text", blank=True)

    class Meta:
        verbose_name = "Mahnstufe"
        verbose_name_plural = "Mahnstufen"
        ordering = ["level"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "level"], name="mahnstufe_einmal")
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        if self.fee is not None and self.fee < 0:
            raise ValidationError({"fee": gettext("Die Gebühr darf nicht negativ sein.")})


def dunning_pdf_path(instance, filename: str) -> str:
    return f"mahnungen/{instance.organization_id}/{instance.pk}-{filename}"


class Dunning(models.Model):
    """Ausgelöste Mahnung zu einer Rechnung."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="dunnings")
    issued_pdf = PrivateFileField(
        storage=private_storage, upload_to=dunning_pdf_path, blank=True, db_default=""
    )
    issued_pdf_sha256 = models.CharField(max_length=64, blank=True, db_default="")
    level = models.PositiveSmallIntegerField("Stufe")
    name = models.CharField("Bezeichnung", max_length=100)
    text = models.TextField("Text", blank=True)
    date = models.DateField("Datum")
    due_date = models.DateField("neue Zahlungsfrist")
    fee = models.DecimalField("Mahngebühr", max_digits=8, decimal_places=2, default=ZERO)
    sent_at = models.DateTimeField("per E-Mail verschickt", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mahnung"
        verbose_name_plural = "Mahnungen"
        ordering = ["date", "level"]

    def __str__(self) -> str:
        return f"{self.name} zu {self.invoice}"


class Mandate(models.Model):
    """SEPA-Lastschriftmandat (Basislastschrift) eines Mitglieds oder Vereins."""

    class Source(models.TextChoices):
        PAPER = "paper", gettext_lazy("schriftlich")
        ONLINE = "online", gettext_lazy("im Mitgliederbereich")

    class Status(models.TextChoices):
        ACTIVE = "active", gettext_lazy("gültig")
        REVOKED = "revoked", gettext_lazy("widerrufen")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    membership = models.ForeignKey(
        "members.Membership",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mandates",
    )
    club = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Verein (Dachverband zieht ein)",
    )
    reference = models.CharField("Mandatsreferenz", max_length=35)
    # Basislastschrift oder Firmenlastschrift (nur Organisationen und Vereine, J8b)
    scheme = models.CharField(
        "Verfahren",
        max_length=4,
        choices=[("CORE", "Basislastschrift"), ("B2B", "Firmenlastschrift")],
        default="CORE",
        db_default="CORE",
    )
    # Verschlüsselt (core/encfields.py)
    holder = EncryptedCharField("Kontoinhaber", max_length=70)
    iban = EncryptedCharField("IBAN", max_length=34)
    bic = EncryptedCharField("BIC", max_length=11, blank=True)
    signed_on = models.DateField("Datum der Unterschrift")
    source = models.CharField("Erteilt", max_length=10, choices=Source.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    revoked_on = models.DateField("widerrufen am", null=True, blank=True)
    last_used_on = models.DateField("zuletzt eingezogen", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "SEPA-Mandat"
        verbose_name_plural = "SEPA-Mandate"
        ordering = ["-signed_on", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "reference"], name="mandatsreferenz_eindeutig"
            ),
            models.CheckConstraint(
                condition=models.Q(membership__isnull=False, club__isnull=True)
                | models.Q(membership__isnull=True, club__isnull=False),
                name="mandat_zahler",
            ),
        ]

    def __str__(self) -> str:
        return self.reference


class DebitRun(models.Model):
    """Lastschriftlauf: eine SEPA-XML-Datei für das Online-Banking."""

    class Status(models.TextChoices):
        CREATED = "created", gettext_lazy("erstellt")
        BOOKED = "booked", gettext_lazy("gebucht")
        CANCELLED = "cancelled", gettext_lazy("verworfen")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    collection_date = models.DateField("Einzugsdatum")
    account = models.ForeignKey(
        "finance.Account", on_delete=models.PROTECT, related_name="+", verbose_name="Konto"
    )
    message_id = models.CharField(max_length=35)
    # Die einmal erzeugte Bankdatei: erneutes Herunterladen liefert genau diese,
    # auch wenn sich Bank- oder Vereinsdaten inzwischen geändert haben
    xml = models.TextField("SEPA-Datei", blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CREATED)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    booked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Lastschriftlauf"
        verbose_name_plural = "Lastschriftläufe"
        ordering = ["-collection_date", "-pk"]

    def __str__(self) -> str:
        return f"Lastschrift {self.collection_date}"


class DebitItem(models.Model):
    class Sequence(models.TextChoices):
        FIRST = "FRST", gettext_lazy("Erstlastschrift")
        RECURRING = "RCUR", gettext_lazy("Folgelastschrift")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    run = models.ForeignKey(DebitRun, on_delete=models.CASCADE, related_name="items")
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="debits")
    mandate = models.ForeignKey(Mandate, on_delete=models.PROTECT, related_name="debits")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    sequence = models.CharField(max_length=4, choices=Sequence.choices)
    end_to_end_id = models.CharField(max_length=35)
    prenotified_at = models.DateTimeField(null=True, blank=True)
    payment = models.OneToOneField(
        Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name="debit"
    )

    class Meta:
        verbose_name = "Lastschrift"
        verbose_name_plural = "Lastschriften"
        ordering = ["pk"]

    def __str__(self) -> str:
        return self.end_to_end_id
