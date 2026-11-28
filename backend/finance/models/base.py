"""Kasse: Konten, Steuerbereiche und Kategorien."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext, gettext_lazy


class TaxArea(models.TextChoices):
    IDEAL = "ideal", gettext_lazy("ideeller Bereich")
    ASSETS = "assets", gettext_lazy("Vermögensverwaltung")
    PURPOSE = "purpose", gettext_lazy("Zweckbetrieb")
    BUSINESS = "business", gettext_lazy("wirtschaftlicher Geschäftsbetrieb")


class Account(models.Model):
    class Kind(models.TextChoices):
        BANK = "bank", gettext_lazy("Bankkonto")
        CASH = "cash", gettext_lazy("Barkasse")
        SAVINGS = "savings", gettext_lazy("Sparkonto")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    name = models.CharField("Name", max_length=100)
    kind = models.CharField("Art", max_length=10, choices=Kind.choices, default=Kind.BANK)
    iban = models.CharField("IBAN", max_length=34, blank=True)
    bic = models.CharField("BIC", max_length=11, blank=True)
    bank_name = models.CharField("Bank", max_length=100, blank=True)
    opening_balance = models.DecimalField(
        "Anfangsbestand", max_digits=12, decimal_places=2, default=Decimal("0")
    )
    opening_date = models.DateField("Stichtag Anfangsbestand")
    is_active = models.BooleanField("aktiv", default=True)
    position = models.PositiveIntegerField("Reihenfolge", default=0)
    # DATEV-Export: Finanzkonto (z. B. 1200 Bank, 1000 Kasse)
    datev_account = models.CharField("DATEV-Konto", max_length=9, blank=True)
    # Direkt bei der Bank abrufen (konzepte „FinTS-Integration“): Zugang und letzter Abruf
    bank_access = models.ForeignKey(
        "finance.BankAccess",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accounts",
        verbose_name="Bankzugang",
    )
    bank_fetched_until = models.DateField("Umsätze abgerufen bis", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Konto"
        verbose_name_plural = "Konten"
        ordering = ["position", "name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "name"], name="konto_name_eindeutig")
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        self.iban = self.iban.replace(" ", "").upper()
        self.bic = self.bic.replace(" ", "").upper()
        if self.iban and not iban_valid(self.iban):
            raise ValidationError({"iban": gettext("Die IBAN ist ungültig.")})


def iban_valid(iban: str) -> bool:
    iban = iban.replace(" ", "").upper()
    if len(iban) < 15 or len(iban) > 34 or not iban[:2].isalpha() or not iban.isalnum():
        return False
    moved = iban[4:] + iban[:4]
    digits = "".join(str(int(c, 36)) for c in moved)
    return int(digits) % 97 == 1


class VatRate(models.TextChoices):
    """Umsatzsteuer einer Buchung bzw. Vorgabe einer Kategorie (Konzept vereinskasse-steuern, S2).

    Der Betrag bleibt brutto; Netto und Steuer werden daraus berechnet."""

    NONE = "", gettext_lazy("keine (nicht steuerbar)")
    EXEMPT = "exempt", gettext_lazy("steuerfrei")
    REDUCED = "7", gettext_lazy("7 %")
    STANDARD = "19", gettext_lazy("19 %")


class Category(models.Model):
    class Kind(models.TextChoices):
        INCOME = "income", gettext_lazy("Einnahmen")
        EXPENSE = "expense", gettext_lazy("Ausgaben")
        BOTH = "both", gettext_lazy("Einnahmen und Ausgaben")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    name = models.CharField("Name", max_length=100)
    kind = models.CharField("Art", max_length=10, choices=Kind.choices, default=Kind.BOTH)
    tax_area = models.CharField(
        "steuerlicher Bereich", max_length=10, choices=TaxArea.choices, blank=True
    )
    is_active = models.BooleanField("aktiv", default=True)
    # Einnahmen dieser Kategorie lassen sich als Zuwendung (Spende) übernehmen
    donations = models.BooleanField("Spenden (Zuwendungsbestätigung möglich)", default=False)
    # Künstlersozialabgabe (Konzept vereinskasse-steuern, S4): Ausgaben dieser Kategorie sind
    # Honorare an selbständige Künstler und Publizisten
    artist_fees = models.BooleanField(
        "Honorare an Künstler (Künstlersozialabgabe)", default=False, db_default=False
    )
    # DATEV-Export: Sachkonto (Gegenkonto der Buchungen dieser Kategorie)
    datev_account = models.CharField("DATEV-Konto", max_length=9, blank=True)
    vat_rate = models.CharField(
        "Umsatzsteuer (Vorgabe)",
        max_length=6,
        choices=VatRate.choices,
        blank=True,
        default="",
        db_default="",
    )

    class Meta:
        verbose_name = "Kategorie"
        verbose_name_plural = "Kategorien"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"], name="kategorie_name_eindeutig"
            )
        ]

    def __str__(self) -> str:
        return self.name

    def allows(self, booking_kind: str) -> bool:
        return self.kind == self.Kind.BOTH or self.kind == booking_kind
