"""Kasse: Rücklagen und Zweckbindungen."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy

from core.encfields import EncryptedCharField


class Reserve(models.Model):
    """Rücklage nach § 62 AO (Finanzamt-Prüfung C4, zuschaltbar).

    Eine Rücklage ist kein Konto: Das Geld bleibt auf den Konten, die Rücklage bindet
    einen Teil davon für einen Zweck. Bewegungen sind Zuführungen und Auflösungen."""

    class Kind(models.TextChoices):
        PURPOSE = "purpose", gettext_lazy("Projektrücklage (§ 62 Abs. 1 Nr. 1 AO)")
        REPLACEMENT = (
            "replacement",
            gettext_lazy("Wiederbeschaffungsrücklage (§ 62 Abs. 1 Nr. 2 AO)"),
        )
        FREE = "free", gettext_lazy("freie Rücklage (§ 62 Abs. 1 Nr. 3 AO)")
        OTHER = "other", gettext_lazy("sonstige Rücklage")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    name = models.CharField("Bezeichnung", max_length=100)
    kind = models.CharField("Art", max_length=12, choices=Kind.choices)
    purpose = models.TextField("Zweck bzw. Vorhaben", max_length=1000, blank=True)
    is_active = models.BooleanField("aktiv", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Rücklage"
        verbose_name_plural = "Rücklagen"
        ordering = ["-is_active", "name"]

    def __str__(self) -> str:
        return self.name


class ReserveMovement(models.Model):
    """Zuführung zu oder Auflösung einer Rücklage."""

    class Direction(models.TextChoices):
        ADD = "add", gettext_lazy("Zuführung")
        RELEASE = "release", gettext_lazy("Auflösung")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    reserve = models.ForeignKey(Reserve, on_delete=models.PROTECT, related_name="movements")
    direction = models.CharField("Art", max_length=10, choices=Direction.choices)
    date = models.DateField("Datum")
    year = models.PositiveSmallIntegerField("Geschäftsjahr")
    amount = models.DecimalField("Betrag", max_digits=12, decimal_places=2)
    note = models.CharField("Begründung", max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_by_name = EncryptedCharField(max_length=200, blank=True, strict=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Rücklagenbewegung"
        verbose_name_plural = "Rücklagenbewegungen"
        ordering = ["date", "pk"]
        indexes = [models.Index(fields=["organization", "year"])]

    def __str__(self) -> str:
        return f"{self.get_direction_display()} {self.reserve} {self.amount} €"

    @property
    def signed(self) -> Decimal:
        return self.amount if self.direction == self.Direction.ADD else -self.amount


class Earmark(models.Model):
    """Zweckbindung für Spenden (Konzept vereinskasse-steuern, S5).

    Spenden „für die neue Fahne“ dürfen nur für diesen Zweck verwendet werden. Die
    Zweckbindung sammelt solche Spenden und die Ausgaben dafür; der Rest zeigt, was noch
    zweckgebunden zu verwenden ist."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    name = models.CharField("Zweck", max_length=100)
    note = models.TextField("Beschreibung", max_length=1000, blank=True)
    is_active = models.BooleanField("aktiv", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Zweckbindung"
        verbose_name_plural = "Zweckbindungen"
        ordering = ["-is_active", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"], name="zweckbindung_name_eindeutig"
            )
        ]

    def __str__(self) -> str:
        return self.name
