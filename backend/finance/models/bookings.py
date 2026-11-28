"""Kasse: Buchungen und Belege."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy

from core.encfields import EncryptedCharField, EncryptedJSONField
from core.i18n import date_text
from core.privatefiles import PrivateFileField
from exchange.models import private_storage

from .base import Account, Category, VatRate


class Booking(models.Model):
    class Kind(models.TextChoices):
        INCOME = "income", gettext_lazy("Einnahme")
        EXPENSE = "expense", gettext_lazy("Ausgabe")
        TRANSFER = "transfer", gettext_lazy("Umbuchung")

    class Allowance(models.TextChoices):
        NONE = "", gettext_lazy("keine")
        TRAINER = "trainer", gettext_lazy("Übungsleiterfreibetrag (§ 3 Nr. 26 EStG)")
        VOLUNTEER = "volunteer", gettext_lazy("Ehrenamtspauschale (§ 3 Nr. 26a EStG)")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    # Geschäftsjahr (Kalenderjahr seines Beginns), siehe Organization.fiscal_year_of
    year = models.PositiveSmallIntegerField("Geschäftsjahr")
    number = models.PositiveIntegerField("Buchungsnummer")
    date = models.DateField("Datum")
    kind = models.CharField("Art", max_length=10, choices=Kind.choices)
    amount = models.DecimalField("Betrag", max_digits=12, decimal_places=2)
    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="bookings", verbose_name="Konto"
    )
    to_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="incoming_transfers",
        null=True,
        blank=True,
        verbose_name="Zielkonto",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="bookings",
        null=True,
        blank=True,
        verbose_name="Kategorie",
    )
    text = EncryptedCharField("Buchungstext", max_length=200, strict=True)
    reference = models.CharField("Belegnummer/Referenz", max_length=100, blank=True)
    # Wer das Geld bekommt (Ausgabe) oder zahlt (Einnahme): Geschäft, Dienstleister,
    # Person. Freitext; frühere Namen werden beim Erfassen vorgeschlagen.
    counterparty = EncryptedCharField("Empfänger/Zahler", max_length=200, blank=True, strict=True)
    # Geschäftspartner (konzepte/geschaeftspartner.md, P2): freiwillig, der Freitext bleibt
    partner = models.ForeignKey(
        "billing.BusinessPartner",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Geschäftspartner",
    )
    membership = models.ForeignKey(
        "members.Membership",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Mitglied",
    )
    department = models.ForeignKey(
        "organizations.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Abteilung",
    )
    # Veranstaltung, zu der die Einnahme oder Ausgabe gehört (nur für die Auswertung)
    project = models.ForeignKey(
        "Project",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="bookings",
        verbose_name="Veranstaltung",
    )
    # Zweckgebundene Spenden (Konzept vereinskasse-steuern, S5): Ausgabe für diesen Zweck
    earmark = models.ForeignKey(
        "Earmark",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="bookings",
        verbose_name="Zweckbindung",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Beim Jahresabschluss festgehalten (Gesamtaudit 31.10.b, Frage 9): spätere Änderungen
    # an der Kategorie verschieben abgeschlossene Jahre nicht mehr.
    frozen = models.BooleanField(default=False)
    frozen_category_name = models.CharField(max_length=100, blank=True, default="")
    frozen_tax_area = models.CharField(max_length=10, blank=True, default="")
    # Storno (GoBD): Gegenbuchung verweist auf die stornierte Buchung; diese bleibt unverändert
    cancels = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cancellation",
        verbose_name="storniert Buchung",
    )
    cancel_reason = models.CharField("Grund des Stornos", max_length=300, blank=True)
    # Splitbuchung: ein Zahlungsvorgang, aufgeteilt auf mehrere Kategorien bzw. Bereiche.
    # Jeder Teil ist eine eigene Buchung; die Teile verweisen auf die erste (Kopf), dort
    # liegen Belege und die Zuordnung zum Kontoumsatz.
    split_of = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="split_parts",
        verbose_name="Teil der Buchung",
    )
    # Aufwandsvergütung an eine Person (Ausgabe): zählt gegen deren Freibetrag im Kalenderjahr
    allowance = models.CharField(
        "Aufwandsvergütung",
        max_length=10,
        choices=Allowance.choices,
        blank=True,
        default="",
        db_default="",
    )
    # Umsatzsteuer im Betrag (S2); Vorsteuer nur außerhalb des ideellen Bereichs, bei
    # gemischt genutzten Ausgaben anteilig
    vat_rate = models.CharField(
        "Umsatzsteuer", max_length=6, choices=VatRate.choices, blank=True, default="", db_default=""
    )
    input_tax_share = models.PositiveSmallIntegerField(
        "Vorsteuer abziehbar (%)",
        default=100,
        db_default=100,
        validators=[MaxValueValidator(100)],
    )
    # Honorar an selbständige Künstler (Künstlersozialabgabe, S4); zählt auch ohne das
    # Kennzeichen, wenn die Kategorie so markiert ist
    artist_fee = models.BooleanField(
        "Honorar an Künstler (Künstlersozialabgabe)", default=False, db_default=False
    )

    class Meta:
        verbose_name = "Buchung"
        verbose_name_plural = "Buchungen"
        ordering = ["-date", "-number"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "year", "number"], name="buchungsnummer_eindeutig"
            ),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="betrag_positiv"),
        ]
        indexes = [
            models.Index(fields=["organization", "date"]),
            models.Index(fields=["organization", "counterparty"]),
        ]

    def __str__(self) -> str:
        return f"{self.display_number} {self.text}"

    @property
    def category_label(self) -> str | None:
        """Kategorie wie beim Abschluss (abgeschlossenes Jahr) bzw. wie heute."""
        if self.frozen:
            return self.frozen_category_name or None
        return self.category.name if self.category_id else None

    @property
    def tax_area_value(self) -> str:
        if self.frozen:
            return self.frozen_tax_area
        return self.category.tax_area if self.category_id else ""

    @property
    def display_number(self) -> str:
        return f"{self.organization.fiscal_label(self.year)}-{self.number:04d}"

    def clean(self):
        errors: dict[str, str] = {}
        self.counterparty = " ".join((self.counterparty or "").split())
        if self.amount is not None and self.amount <= 0:
            errors["amount"] = gettext("Der Betrag muss größer als 0 sein.")
        if self.kind == self.Kind.TRANSFER:
            if not self.to_account_id:
                errors["to_account"] = gettext("Bitte das Zielkonto wählen.")
            elif self.to_account_id == self.account_id:
                errors["to_account"] = gettext("Zielkonto und Konto müssen verschieden sein.")
            self.category = None
            self.project = None
            self.counterparty = ""
        else:
            self.to_account = None
            if not self.category_id:
                errors["category"] = gettext("Bitte eine Kategorie wählen.")
            elif not self.category.allows(self.kind):
                errors["category"] = gettext("Die Kategorie passt nicht zu dieser Art der Buchung.")
        if self.artist_fee and self.kind != self.Kind.EXPENSE:
            errors["artist_fee"] = gettext("Ein Künstlerhonorar ist immer eine Ausgabe.")
        if self.vat_rate and self.kind == self.Kind.TRANSFER:
            errors["vat_rate"] = gettext("Eine Umbuchung enthält keine Umsatzsteuer.")
        if self.earmark_id and self.kind != self.Kind.EXPENSE:
            errors["earmark"] = gettext("Eine Zweckbindung gibt es nur für Ausgaben.")
        if self.allowance and self.kind != self.Kind.EXPENSE:
            errors["allowance"] = gettext("Eine Aufwandsvergütung ist immer eine Ausgabe.")
        elif (
            self.allowance
            and not self.membership_id
            and not self.counterparty
            # Auszahlung aus der Musikerabrechnung: die Person steht in der Musikerakte
            and not (self.pk and hasattr(self, "performance_expense"))
        ):
            errors["allowance"] = gettext(
                "Bitte das Mitglied oder den Empfänger angeben, damit die Vergütung der "
                "richtigen Person zugerechnet wird."
            )
        if self.date and self.account_id and self.date < self.account.opening_date:
            errors["date"] = gettext(
                "Das Datum liegt vor dem Stichtag des Anfangsbestands von „{x0}“ ({x1})."
            ).format(x0=self.account.name, x1=date_text(self.account.opening_date))
        if (
            self.date
            and self.to_account_id
            and self.to_account_id != self.account_id
            and self.date < self.to_account.opening_date
        ):
            errors["date"] = gettext("Das Datum liegt vor dem Stichtag des Zielkontos.")
        if (
            self.project_id
            and self.organization_id
            and self.project.organization_id != self.organization_id
        ):
            errors["project"] = gettext("Unbekannte Veranstaltung.")
        if errors:
            raise ValidationError(errors)

    def effect_on(self, account_id: int) -> Decimal:
        """Wie die Buchung den Bestand eines Kontos verändert."""
        if self.kind == self.Kind.INCOME:
            return self.amount if self.account_id == account_id else Decimal("0")
        if self.kind == self.Kind.EXPENSE:
            return -self.amount if self.account_id == account_id else Decimal("0")
        result = Decimal("0")
        if self.account_id == account_id:
            result -= self.amount
        if self.to_account_id == account_id:
            result += self.amount
        return result


def receipt_path(instance, filename: str) -> str:
    stamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
    return f"receipts/{instance.organization_id}/{stamp}-{filename}"


class Receipt(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    booking = models.ForeignKey(
        Booking, on_delete=models.CASCADE, related_name="receipts", verbose_name="Buchung"
    )
    file = PrivateFileField("Datei", storage=private_storage, upload_to=receipt_path)
    name = models.CharField("Dateiname", max_length=200)
    content_type = models.CharField("Dateityp", max_length=100)
    size = models.PositiveIntegerField("Größe", default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Ausgeblendet statt gelöscht (Aufbewahrungspflicht): Datei bleibt, steht im Export
    hidden_at = models.DateTimeField("ausgeblendet am", null=True, blank=True)
    hidden_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    hidden_reason = models.CharField("Grund", max_length=300, blank=True)
    # E-Rechnung (XRechnung, ZUGFeRD): ausgelesene Angaben; maßgeblich bleibt die Datei
    einvoice = EncryptedJSONField("E-Rechnung", default=dict, blank=True, strict=True)

    class Meta:
        verbose_name = "Beleg"
        verbose_name_plural = "Belege"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return self.name
