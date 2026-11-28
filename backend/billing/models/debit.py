"""Abrechnung: SEPA-Mandate und Lastschriftläufe."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy

from core.encfields import (
    EncryptedCharField,
    EncryptedTextField,
)

from .invoices import Invoice, Payment


class Mandate(models.Model):
    """SEPA-Lastschriftmandat eines Mitglieds, eines Vereins oder des Zahlers eines
    Haushalts bzw. einer Firma."""

    class Source(models.TextChoices):
        PAPER = "paper", gettext_lazy("schriftlich")
        ONLINE = "online", gettext_lazy("im Mitgliederbereich")
        APPLICATION = "application", gettext_lazy("im Online-Antrag")

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
    # Zahler eines Haushalts oder einer Firma ohne eigene Mitgliedschaft (H2)
    household = models.ForeignKey(
        "members.Household",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mandates",
        verbose_name="Haushalt/Firma",
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
    source = models.CharField("Erteilt", max_length=12, choices=Source.choices)
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
                condition=models.Q(
                    membership__isnull=False, club__isnull=True, household__isnull=True
                )
                | models.Q(membership__isnull=True, club__isnull=False, household__isnull=True)
                | models.Q(membership__isnull=True, club__isnull=True, household__isnull=False),
                name="mandat_zahler_haushalt",
            ),
            # Höchstens ein gültiges Mandat je Zahler, auch bei gleichzeitigen Anfragen (B-M07)
            models.UniqueConstraint(
                fields=["organization", "membership"],
                condition=models.Q(membership__isnull=False, status="active"),
                name="mandat_aktiv_mitglied",
            ),
            models.UniqueConstraint(
                fields=["organization", "club"],
                condition=models.Q(club__isnull=False, status="active"),
                name="mandat_aktiv_verein",
            ),
            models.UniqueConstraint(
                fields=["organization", "household"],
                condition=models.Q(household__isnull=False, status="active"),
                name="mandat_aktiv_haushalt",
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
    xml = EncryptedTextField("SEPA-Datei", blank=True, default="")
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
