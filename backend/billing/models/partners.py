"""Abrechnung: Geschäftspartner, Ansprechpersonen, Zusatzfelder, Vereinbarungen und Dokumente."""

from __future__ import annotations

import uuid

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
from core.versioning import Versioned
from exchange.models import private_storage


class BusinessPartner(Versioned):
    """Geschäftspartner: Firmen, Behörden, Vereine und Personen außerhalb der Mitgliederliste.

    Konzept konzepte/geschaeftspartner.md (P1). ``details`` folgt dem Schema der
    E-Rechnung (Anschrift, E-Mail, Steuerangaben); für eine Rechnung wird es dort
    vollständig geprüft. ``is_customer``/``is_supplier`` folgen aus ``roles``.
    """

    # Fassung zählt nur hoch: nicht protokollieren, nicht zurückspielen (core/versioning.py)
    derived_fields = ("version",)

    class Kind(models.TextChoices):
        COMPANY = "company", gettext_lazy("Firma")
        AUTHORITY = "authority", gettext_lazy("Behörde/Amt")
        ASSOCIATION = "association", gettext_lazy("Verein/Verband")
        PERSON = "person", gettext_lazy("Privatperson")
        OTHER = "other", gettext_lazy("Sonstiges")

    class Role(models.TextChoices):
        SUPPLIER = "supplier", gettext_lazy("Lieferant")
        SERVICE = "service", gettext_lazy("Dienstleister")
        CUSTOMER = "customer", gettext_lazy("Kunde/Auftraggeber")
        SPONSOR = "sponsor", gettext_lazy("Sponsor")
        DONOR = "donor", gettext_lazy("Spender")
        VENUE = "venue", gettext_lazy("Vermieter/Veranstaltungsort")
        ARTIST = "artist", gettext_lazy("Künstler/Musiker")
        AUTHORITY = "authority", gettext_lazy("Behörde")
        PRESS = "press", gettext_lazy("Presse")
        INSURANCE = "insurance", gettext_lazy("Versicherung")
        BANK = "bank", gettext_lazy("Bank")
        # Datenschutz-Werkzeuge (Lückenliste 20.11.2026, B5)
        PROCESSOR = "processor", gettext_lazy("Auftragsverarbeiter")

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    name = EncryptedCharField(max_length=200, strict=True)
    kind = models.CharField(
        max_length=12, choices=Kind.choices, default=Kind.COMPANY, db_default=Kind.COMPANY
    )
    roles = models.JSONField(default=list, db_default=[], blank=True)
    # Eigene Partnernummer, z. B. „GP-0012“ (GP-12)
    number = models.CharField(max_length=20, blank=True, default="", db_default="")
    # Zuständige Einheit im Datenbereich (Verein oder Untereinheit ohne eigenen Bereich)
    unit = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    # Ist der Geschäftspartner auch Mitglied, wird verwiesen statt kopiert (GP-4)
    membership = models.ForeignKey(
        "members.Membership",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="business_partners",
    )
    # Wie der Kontakt zustande kam (Wunsch 11.11.): Datum und kurzer Text
    first_contact_on = models.DateField("Erstkontakt am", null=True, blank=True)
    first_contact_note = EncryptedCharField(
        "Erstkontakt", max_length=300, blank=True, default="", db_default="", strict=True
    )
    # Mitglied des Vereins, das den Kontakt hält
    liaison = models.ForeignKey(
        "members.Membership",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Betreut von",
    )
    is_customer = models.BooleanField(default=True)
    is_supplier = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    # Ein Schema für Kunden, Lieferanten und die eingefrorenen Rechnungsanschriften.
    details = EncryptedJSONField(default=dict, strict=True)
    # Nur mit Kassen- oder Beitragsrecht sichtbar (GP-3)
    bank = EncryptedJSONField(default=dict, db_default={}, blank=True, strict=True)
    our_customer_number = EncryptedCharField(
        max_length=60, blank=True, default="", db_default="", strict=True
    )
    default_category = models.ForeignKey(
        "finance.Category", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    payment_terms_days = models.PositiveSmallIntegerField(null=True, blank=True)
    # Künstler/Publizist nach KSVG: Ausgaben zählen für die Künstlersozialabgabe
    artist = models.BooleanField(default=False, db_default=False)
    notes = EncryptedTextField(max_length=5000, blank=True, default="", db_default="")
    # Webseite (P4): nur mit Einwilligung als Partner/Sponsor auf der Vereinsseite nennen
    website_consent = models.BooleanField(default=False, db_default=False)
    website_url = models.URLField(max_length=300, blank=True, default="", db_default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["pk"]
        verbose_name = gettext_lazy("Geschäftspartner")
        constraints = [
            # Gesamtaudit 15.11., PF-25: keine doppelte Partnernummer je Einheit
            models.UniqueConstraint(
                fields=["organization", "number"],
                condition=~models.Q(number=""),
                name="partner_nummer_eindeutig",
            )
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        roles = set(self.roles or [])
        if roles:
            self.is_customer = self.Role.CUSTOMER in roles
            self.is_supplier = bool(roles & {self.Role.SUPPLIER, self.Role.SERVICE})
        if self.Role.ARTIST in roles:
            self.artist = True
        super().save(*args, **kwargs)


class PartnerContact(Versioned):
    """Ansprechpartner bei einem Geschäftspartner (P1), wie ``members.ContactPerson``."""

    # Fassung zählt nur hoch: nicht protokollieren, nicht zurückspielen (core/versioning.py)
    derived_fields = ("version",)

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    partner = models.ForeignKey(BusinessPartner, on_delete=models.CASCADE, related_name="contacts")
    last_name = EncryptedCharField("Name", max_length=100, strict=True)
    first_name = EncryptedCharField("Vorname", max_length=100, blank=True, strict=True)
    function = EncryptedCharField("Funktion", max_length=100, blank=True, strict=True)
    email = EncryptedEmailField("E-Mail-Adresse", blank=True, strict=True)
    phone = EncryptedCharField("Telefon", max_length=50, blank=True, strict=True)
    is_primary = models.BooleanField("Hauptansprechpartner", default=False)
    receives_invoices = models.BooleanField("erhält Rechnungen", default=False)
    receives_mail = models.BooleanField("erhält Post", default=True)
    notes = EncryptedCharField("Notiz", max_length=500, blank=True, strict=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_primary", "pk"]
        verbose_name = gettext_lazy("Ansprechpartner")

    def __str__(self):
        return " ".join(p for p in (self.first_name, self.last_name) if p)


class PartnerField(models.Model):
    """Zusatzfeld für Geschäftspartner, aufgebaut wie die Zusatzfelder der Mitglieder."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    label = models.CharField("Bezeichnung", max_length=100)
    key = models.SlugField("Kennung", max_length=50)
    field_type = models.CharField("Typ", max_length=10, default="text")
    choices = models.JSONField("Auswahlwerte", default=list, blank=True)
    repeatable = models.BooleanField("wiederholbar", default=False)
    subfields = models.JSONField("Unterfelder", default=list, blank=True)
    help_text = models.CharField("Hinweis", max_length=200, blank=True)
    sort_order = models.PositiveSmallIntegerField("Reihenfolge", default=0)
    is_archived = models.BooleanField("nicht mehr verwendet", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Zusatzfeld für Geschäftspartner")
        ordering = ["sort_order", "label"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "key"], name="partnerfeld_kennung_je_org"
            )
        ]

    def __str__(self):
        return self.label

    def clean(self):
        from customfields.models import TYPE_KEYS, structure_errors

        errors = structure_errors(self)
        if not self.repeatable and self.field_type not in TYPE_KEYS:
            errors["field_type"] = gettext("Unbekannter Feldtyp.")
        if errors:
            raise ValidationError(errors)


class PartnerFieldValue(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    definition = models.ForeignKey(PartnerField, on_delete=models.CASCADE, related_name="values")
    partner = models.ForeignKey(
        BusinessPartner, on_delete=models.CASCADE, related_name="field_values"
    )
    value = EncryptedJSONField(null=True, blank=True, strict=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Zusatzfeld-Wert eines Geschäftspartners")
        constraints = [
            models.UniqueConstraint(fields=["definition", "partner"], name="partnerfeldwert_einmal")
        ]

    def __str__(self):
        return f"{self.definition}: {self.value}"


class PartnerAgreement(Versioned):
    """Sponsoring- oder Rahmenvereinbarung mit einem Geschäftspartner (P4).

    ``tax_kind`` hält fest, wie die Einnahme steuerlich einzuordnen ist: bloße Nennung
    (ideeller Bereich bzw. Vermögensverwaltung) oder aktive Werbung (wirtschaftlicher
    Geschäftsbetrieb). Mit Enddatum legt HUBIplan eine Aufgabe zur Verlängerung an."""

    # Fassung zählt nur hoch: nicht protokollieren, nicht zurückspielen (core/versioning.py)
    derived_fields = ("version",)

    class Kind(models.TextChoices):
        SPONSORING = "sponsoring", gettext_lazy("Sponsoring")
        FRAMEWORK = "framework", gettext_lazy("Rahmenvereinbarung")
        CONTRACT = "contract", gettext_lazy("Vertrag")
        DPA = "dpa", gettext_lazy("Auftragsverarbeitungsvertrag")
        OTHER = "other", gettext_lazy("Sonstige Vereinbarung")

    class TaxKind(models.TextChoices):
        MENTION = "mention", gettext_lazy("Nur Nennung (ohne Werbung)")
        ADVERTISING = "advertising", gettext_lazy("Aktive Werbung")
        NONE = "none", gettext_lazy("Keine Einnahme")

    class Benefit(models.TextChoices):
        WEBSITE = "website", gettext_lazy("Logo auf der Webseite")
        BANNER = "banner", gettext_lazy("Bande oder Banner")
        PUBLICATION = "publication", gettext_lazy("Festschrift oder Programmheft")
        CLOTHING = "clothing", gettext_lazy("Trikot oder Kleidung")
        EVENT = "event", gettext_lazy("Nennung bei Veranstaltungen")
        OTHER = "other", gettext_lazy("Sonstiges")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    partner = models.ForeignKey(
        BusinessPartner, on_delete=models.CASCADE, related_name="agreements"
    )
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.SPONSORING)
    title = models.CharField(max_length=200)
    start = models.DateField()
    end = models.DateField(null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    in_kind = models.CharField(max_length=300, blank=True, default="")
    benefits = models.JSONField(default=list, blank=True)
    benefits_text = models.CharField(max_length=500, blank=True, default="")
    tax_kind = models.CharField(max_length=12, choices=TaxKind.choices, default=TaxKind.MENTION)
    category = models.ForeignKey(
        "finance.Category", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Verträge (P5): Kündigungsfrist vor dem Ende, stillschweigende Verlängerung
    notice_days = models.PositiveSmallIntegerField(null=True, blank=True)
    auto_renew = models.BooleanField(default=False, db_default=False)
    remind_days = models.PositiveSmallIntegerField(default=60)
    reminder = models.ForeignKey(
        "todos.Todo", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    thanked_at = models.DateField(null=True, blank=True)
    notes = EncryptedTextField(max_length=2000, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start", "pk"]
        verbose_name = gettext_lazy("Vereinbarung")

    def __str__(self):
        return self.title


def partner_document_path(instance, filename):
    return f"geschaeftspartner/{instance.organization_id}/{uuid.uuid4().hex}/{filename}"


class PartnerDocument(models.Model):
    """Datei an der Partnerakte (P5): Vertrag, Angebot, Einwilligung, Schriftverkehr."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    partner = models.ForeignKey(BusinessPartner, on_delete=models.CASCADE, related_name="documents")
    agreement = models.ForeignKey(
        PartnerAgreement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )
    title = EncryptedCharField(max_length=200, blank=True, strict=True)
    name = models.CharField(max_length=200)
    content_type = models.CharField(max_length=100)
    size = models.PositiveIntegerField(default=0)
    file = PrivateFileField(storage=private_storage, upload_to=partner_document_path)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at", "pk"]
        verbose_name = gettext_lazy("Dokument zum Geschäftspartner")

    def __str__(self):
        return self.title or self.name
