"""Abrechnung: Zahler und Beitragsregeln für Haushalte."""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy

from core.encfields import (
    EncryptedCharField,
    EncryptedEmailField,
)
from members.models import Household

from .partners import BusinessPartner


class HouseholdPayer(models.Model):
    """Wer für einen Haushalt oder eine Firma zahlt (Konzept Familien, Haushalte und
    Firmen, H2). Fehlt der Eintrag, gehen die Beiträge wie bisher (selbst oder Zug).

    - ``member``: ein Mitglied (meist des Haushalts) mit eigener Anschrift und Mandat
    - ``external``: eine Person ohne Mitgliedschaft (Elternteil, Großeltern); Anschrift
      und Mail stehen hier, das Mandat hängt am Haushalt
    - ``organization``: ein Organisationsmitglied (Firma ist auch Mitglied)
    - ``partner``: ein Geschäftspartner (Firma ist nicht Mitglied); Mandat am Haushalt
    """

    class Kind(models.TextChoices):
        MEMBER = "member", gettext_lazy("Mitglied")
        EXTERNAL = "external", gettext_lazy("Person ohne Mitgliedschaft")
        ORGANIZATION = "organization", gettext_lazy("Organisationsmitglied")
        PARTNER = "partner", gettext_lazy("Geschäftspartner")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    household = models.OneToOneField(
        "members.Household", on_delete=models.CASCADE, related_name="payer"
    )
    kind = models.CharField("Zahler", max_length=12, choices=Kind.choices)
    membership = models.ForeignKey(
        "members.Membership",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="zahlendes Mitglied",
    )
    partner = models.ForeignKey(
        BusinessPartner,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Geschäftspartner",
    )
    name = EncryptedCharField("Name", max_length=200, blank=True)
    attention = EncryptedCharField("z. Hd.", max_length=200, blank=True)
    street = EncryptedCharField("Straße oder Postfach", max_length=200, blank=True)
    postal_code = EncryptedCharField("PLZ", max_length=20, blank=True)
    city = EncryptedCharField("Ort", max_length=100, blank=True)
    country = models.CharField("Land", max_length=100, blank=True, default="")
    email = EncryptedEmailField("E-Mail-Adresse", blank=True)
    order_reference = models.CharField("Bestellnummer", max_length=100, blank=True, default="")
    leitweg_id = models.CharField("Leitweg-ID", max_length=50, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Zahler eines Haushalts"
        verbose_name_plural = "Zahler von Haushalten"

    def __str__(self) -> str:
        return f"Zahler {self.pk}"


class HouseholdFeeRule(models.Model):
    """Familien- bzw. Firmenbeitrag (H3): wirkt auf die Summe der Einzelbeiträge einer
    Haushalts- oder Firmenrechnung. Die Einzelbeiträge rechnet der Beitragslauf wie bisher.

    - ``cap``: höchstens ``amount`` je Rechnung
    - ``flat``: genau ``amount`` (nie mehr als die Summe), ab ``min_persons``
    - ``stagger``: zweite Person ``second_percent`` % weniger, ab der dritten
      ``third_percent`` % weniger (teuerste Beiträge zuerst)
    """

    class Mode(models.TextChoices):
        NONE = "none", gettext_lazy("keine Ermäßigung")
        CAP = "cap", gettext_lazy("Höchstbetrag")
        FLAT = "flat", gettext_lazy("Pauschale")
        STAGGER = "stagger", gettext_lazy("Staffel")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    kind = models.CharField("für", max_length=10, choices=Household.Kind.choices)
    mode = models.CharField("Form", max_length=10, choices=Mode.choices, default=Mode.NONE)
    amount = models.DecimalField(
        "Betrag je Jahr", max_digits=10, decimal_places=2, null=True, blank=True
    )
    min_persons = models.PositiveSmallIntegerField("ab Personen", default=2)
    adult_required = models.BooleanField("mindestens ein Erwachsener", default=False)
    second_percent = models.DecimalField(
        "zweite Person weniger (%)", max_digits=5, decimal_places=2, default=0
    )
    third_percent = models.DecimalField(
        "ab der dritten Person weniger (%)", max_digits=5, decimal_places=2, default=0
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Familien- bzw. Firmenbeitrag"
        verbose_name_plural = "Familien- und Firmenbeiträge"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "kind"], name="ein_familienbeitrag_je_art"
            )
        ]

    def __str__(self) -> str:
        return f"Familienbeitrag {self.pk}"
