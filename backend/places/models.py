"""Gespeicherte Orte (konzepte/termin-rundschreiben-rueckmeldung.md, Baustein O1).

Ein Ort gehört einem Dachverband oder Verein. Vereine sehen zusätzlich die Orte ihres
Dachverbands, Untereinheiten die ihres Vereins. Termine, Wettbewerbe, Helferdienste und
Versammlungen übernehmen beim Auswählen eine Kopie von Name und Anschrift; ändert sich
ein Ort später, bleiben alte Einträge, wie sie waren.
"""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class Place(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    name = models.CharField(_("Name"), max_length=200)
    address = models.CharField(_("Anschrift"), max_length=300, blank=True)
    directions = models.TextField(_("Anfahrt und Hinweise"), max_length=1000, blank=True)
    latitude = models.DecimalField(
        _("Breite"),
        max_digits=8,
        decimal_places=5,
        null=True,
        blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        _("Länge"),
        max_digits=8,
        decimal_places=5,
        null=True,
        blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    is_active = models.BooleanField(_("aktiv"), default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Ort")
        verbose_name_plural = _("Orte")
        ordering = ["name", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "name"], name="ort_name_je_org")
        ]

    def __str__(self) -> str:
        return self.name
