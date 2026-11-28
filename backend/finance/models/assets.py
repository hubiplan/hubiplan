"""Kasse: Anlagenverzeichnis."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext, gettext_lazy

from .base import TaxArea
from .bookings import Booking


class FixedAsset(models.Model):
    """Anlage im Anlagenverzeichnis (Konzept vereinskasse-steuern, Abschnitt 5).

    Die Abschreibung (AfA) erscheint nur in der steuerlichen Auswertung, nie im Kassenbuch:
    Das Kassenbuch bleibt eine reine Zahlungsrechnung. Verknüpft mit der Ausgabe der
    Anschaffung (Beleg) und optional mit dem Gegenstand im Inventar."""

    class Method(models.TextChoices):
        NONE = "none", gettext_lazy("keine Abschreibung (nur Verzeichnis)")
        GWG = "gwg", gettext_lazy("geringwertig, sofort abschreiben (bis 800 € netto)")
        POOL = "pool", gettext_lazy("Sammelposten über 5 Jahre (250 bis 1.000 € netto)")
        LINEAR = "linear", gettext_lazy("linear über die Nutzungsdauer")

    class Disposal(models.TextChoices):
        NONE = "", gettext_lazy("im Bestand")
        SOLD = "sold", gettext_lazy("verkauft")
        SCRAPPED = "scrapped", gettext_lazy("verschrottet bzw. verloren")
        GIVEN = "given", gettext_lazy("verschenkt")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    name = models.CharField("Bezeichnung", max_length=150)
    acquired_on = models.DateField("Anschaffungsdatum")
    # AfA-Basis: ohne abziehbare Vorsteuer; ohne Vorsteuerabzug also der Bruttobetrag
    cost = models.DecimalField("Anschaffungskosten", max_digits=12, decimal_places=2)
    net_cost = models.DecimalField(
        "Nettobetrag", max_digits=12, decimal_places=2, null=True, blank=True
    )
    tax_area = models.CharField(
        "steuerlicher Bereich", max_length=10, choices=TaxArea.choices, default=TaxArea.IDEAL
    )
    method = models.CharField(
        "Abschreibung", max_length=10, choices=Method.choices, default=Method.LINEAR
    )
    useful_life = models.PositiveSmallIntegerField("Nutzungsdauer in Jahren", default=5)
    booking = models.ForeignKey(
        Booking,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fixed_assets",
        verbose_name="Ausgabe der Anschaffung",
    )
    material_item = models.ForeignKey(
        "materials.MaterialItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Gegenstand im Inventar",
    )
    disposal = models.CharField(
        "Abgang", max_length=10, choices=Disposal.choices, blank=True, default=""
    )
    disposed_on = models.DateField("Abgangsdatum", null=True, blank=True)
    note = models.CharField("Notiz", max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Anlage"
        verbose_name_plural = "Anlagen"
        ordering = ["-acquired_on", "name"]
        constraints = [
            models.CheckConstraint(condition=models.Q(cost__gt=0), name="anlage_kosten_positiv"),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def threshold_amount(self) -> Decimal:
        """Betrag für die Grenzen von GWG und Sammelposten (netto)."""
        return self.net_cost if self.net_cost is not None else self.cost

    def clean(self):
        errors: dict[str, str] = {}
        net = self.threshold_amount if self.cost is not None else None
        if self.cost is not None and self.cost <= 0:
            errors["cost"] = gettext("Der Betrag muss größer als 0 sein.")
        if net is not None and self.method == self.Method.GWG and net > Decimal("800"):
            errors["method"] = gettext(
                "Sofort abschreiben lässt sich nur bis 800 € netto (§ 6 Abs. 2 EStG)."
            )
        if (
            net is not None
            and self.method == self.Method.POOL
            and not Decimal("250") < net <= Decimal("1000")
        ):
            errors["method"] = gettext(
                "Ein Sammelposten gilt für 250,01 bis 1.000 € netto (§ 6 Abs. 2a EStG)."
            )
        if self.method == self.Method.LINEAR and not 1 <= (self.useful_life or 0) <= 50:
            errors["useful_life"] = gettext("Bitte eine Nutzungsdauer von 1 bis 50 Jahren angeben.")
        if self.disposal and not self.disposed_on:
            errors["disposed_on"] = gettext("Bitte das Datum des Abgangs angeben.")
        if not self.disposal:
            self.disposed_on = None
        if self.disposed_on and self.acquired_on and self.disposed_on < self.acquired_on:
            errors["disposed_on"] = gettext("Der Abgang liegt vor der Anschaffung.")
        if (
            self.booking_id
            and self.organization_id
            and self.booking.organization_id != self.organization_id
        ):
            errors["booking"] = gettext("Unbekannte Buchung.")
        if errors:
            raise ValidationError(errors)
