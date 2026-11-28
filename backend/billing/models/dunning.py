"""Abrechnung: Mahnstufen und Mahnungen."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext

from core.privatefiles import PrivateFileField
from exchange.models import private_storage

from .invoices import Invoice
from .settings import ZERO


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
