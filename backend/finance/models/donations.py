"""Kasse: Zuwendungsbestätigungen und Spenden."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy

from core.encfields import EncryptedCharField, EncryptedJSONField
from core.privatefiles import PrivateFileField
from exchange.models import private_storage

from .bookings import Booking


class DonationSettings(models.Model):
    """Angaben zur Steuerbegünstigung, die auf jeder Zuwendungsbestätigung stehen."""

    class Notice(models.TextChoices):
        EXEMPTION = (
            "exemption",
            gettext_lazy("Freistellungsbescheid bzw. Anlage zum Körperschaftsteuerbescheid"),
        )
        STATUTE = "statute", gettext_lazy("Feststellung der Satzungsmäßigkeit nach § 60a AO")

    organization = models.OneToOneField(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    # Steuerbegünstigt mit eigenem Bescheid: entscheidet, nicht der Registereintrag
    # (auch nicht eingetragene Vereine können gemeinnützig sein, § 1 Abs. 1 Nr. 5 KStG)
    enabled = models.BooleanField("steuerbegünstigt mit eigenem Bescheid", default=False)
    purposes = models.TextField(
        "begünstigte Zwecke",
        max_length=1000,
        blank=True,
        help_text="z. B. Förderung des traditionellen Brauchtums (§ 52 Abs. 2 Satz 1 Nr. 23 AO)",
    )
    notice = models.CharField(
        "Art des Bescheids", max_length=10, choices=Notice.choices, default=Notice.EXEMPTION
    )
    tax_office = models.CharField("Finanzamt", max_length=200, blank=True)
    tax_number = models.CharField("Steuernummer", max_length=50, blank=True)
    notice_date = models.DateField("Datum des Bescheids", null=True, blank=True)
    assessment_period = models.CharField(
        "letzter Veranlagungszeitraum", max_length=50, blank=True, help_text="z. B. 2022 bis 2024"
    )
    fees_allowed = models.BooleanField("Mitgliedsbeiträge bestätigen", default=False)
    place = models.CharField("Ort der Ausstellung", max_length=100, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Einstellungen Zuwendungsbestätigungen"
        verbose_name_plural = "Einstellungen Zuwendungsbestätigungen"

    def __str__(self) -> str:
        return f"Zuwendungsbestätigungen {self.organization_id}"


def donation_statement_path(instance, filename: str) -> str:
    stamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
    return f"donations/{instance.organization_id}/{stamp}-{filename}"


class DonationStatement(models.Model):
    """Ausgestellte Zuwendungsbestätigung; das PDF ist das Doppel (§ 50 Abs. 7 EStDV)."""

    class Kind(models.TextChoices):
        SINGLE = "single", gettext_lazy("Einzelbestätigung")
        COLLECTIVE = "collective", gettext_lazy("Sammelbestätigung")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    year = models.PositiveSmallIntegerField("Jahr")
    seq = models.PositiveIntegerField("laufende Nummer")
    kind = models.CharField("Art", max_length=10, choices=Kind.choices)
    goods = models.BooleanField("Sachzuwendung", default=False)
    membership = models.ForeignKey(
        "members.Membership",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    donor_name = EncryptedCharField("Zuwendender", max_length=200, strict=True)
    donor_address = models.TextField("Anschrift", max_length=500, blank=True)
    total = models.DecimalField("Betrag", max_digits=12, decimal_places=2)
    period_from = models.DateField("von")
    period_to = models.DateField("bis")
    # Die bestätigten Zuwendungen, wie sie beim Ausstellen galten
    items = EncryptedJSONField(default=list, blank=True, strict=True)
    issued_on = models.DateField("ausgestellt am")
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    signer_name = EncryptedCharField("unterschrieben von", max_length=200, blank=True, strict=True)
    file = PrivateFileField(
        "Doppel", storage=private_storage, upload_to=donation_statement_path, blank=True
    )
    pdf_sha256 = models.CharField(max_length=64, blank=True)
    cancelled_at = models.DateTimeField("storniert am", null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    cancel_reason = models.CharField("Grund des Stornos", max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Zuwendungsbestätigung"
        verbose_name_plural = "Zuwendungsbestätigungen"
        ordering = ["-year", "-seq"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "year", "seq"], name="zuwendungsbestaetigung_nummer"
            )
        ]

    def __str__(self) -> str:
        return f"Zuwendungsbestätigung {self.number}"

    @property
    def number(self) -> str:
        return f"ZB-{self.year}-{self.seq:04d}"


class Donation(models.Model):
    """Eine Zuwendung (Geld, Mitgliedsbeitrag oder Sache), bestätigt oder noch offen."""

    class Kind(models.TextChoices):
        MONEY = "money", gettext_lazy("Geldzuwendung")
        FEE = "fee", gettext_lazy("Mitgliedsbeitrag")
        GOODS = "goods", gettext_lazy("Sachzuwendung")

    class Origin(models.TextChoices):
        BUSINESS = "business", gettext_lazy("aus dem Betriebsvermögen")
        PRIVATE = "private", gettext_lazy("aus dem Privatvermögen")
        UNKNOWN = "unknown", gettext_lazy("keine Angaben zur Herkunft")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    date = models.DateField("Tag der Zuwendung")
    kind = models.CharField("Art", max_length=10, choices=Kind.choices, default=Kind.MONEY)
    amount = models.DecimalField("Betrag bzw. Wert", max_digits=12, decimal_places=2)
    waiver = models.BooleanField("Verzicht auf Erstattung von Aufwendungen", default=False)
    # Verzicht auf eine Pauschale (S3): zählt wie eine Auszahlung gegen den Freibetrag
    allowance = models.CharField(
        "Verzicht auf Aufwandsvergütung",
        max_length=10,
        choices=Booking.Allowance.choices,
        blank=True,
        default="",
        db_default="",
    )
    membership = models.ForeignKey(
        "members.Membership",
        verbose_name="Mitglied",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    partner = models.ForeignKey(
        "billing.BusinessPartner",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Geschäftspartner",
    )
    donor_name = EncryptedCharField("Zuwendender", max_length=200, strict=True)
    donor_address = models.TextField("Anschrift", max_length=500, blank=True)
    goods_description = models.TextField(
        "Bezeichnung der Sache (Alter, Zustand, Kaufpreis)", max_length=1000, blank=True
    )
    goods_origin = models.CharField(
        "Herkunft der Sache", max_length=10, choices=Origin.choices, blank=True
    )
    goods_documents = models.BooleanField("Unterlagen zur Wertermittlung liegen vor", default=False)
    booking = models.OneToOneField(
        Booking,
        verbose_name="Buchung",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="donation",
    )
    note = models.CharField("Notiz", max_length=300, blank=True)
    # Zweckgebundene Spende (Konzept vereinskasse-steuern, S5)
    earmark = models.ForeignKey(
        "Earmark",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="donations",
        verbose_name="Zweckbindung",
    )
    statement = models.ForeignKey(
        DonationStatement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="donations",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Zuwendung"
        verbose_name_plural = "Zuwendungen"
        ordering = ["-date", "-pk"]
        indexes = [models.Index(fields=["organization", "date"])]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.amount} € von {self.donor_name}"
