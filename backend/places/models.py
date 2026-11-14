"""Gespeicherte Orte (konzepte/termin-rundschreiben-rueckmeldung.md, Baustein O1).

Ein Ort gehört einem Dachverband oder Verein. Vereine sehen zusätzlich die Orte ihres
Dachverbands, Untereinheiten die ihres Vereins. Termine, Wettbewerbe, Helferdienste und
Versammlungen übernehmen beim Auswählen eine Kopie von Name und Anschrift; ändert sich
ein Ort später, bleiben alte Einträge, wie sie waren.

Ein Ort kann Räume haben (eine Ebene): Das Gebäude trägt Anschrift, Anfahrt und
Kartenpunkt, der Raum nur seinen Namen und auf Wunsch einen eigenen Hinweis. Zur Auswahl
steht ein Raum als „Gebäude, Raum“ mit der Anschrift des Gebäudes.
"""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


class Place(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    # Gesetzt: Raum in diesem Ort (Gebäude); Räume haben selbst keine Räume
    parent = models.ForeignKey(
        "self",
        verbose_name=_("Gebäude"),
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="rooms",
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
            models.UniqueConstraint(
                fields=["organization", "name"],
                condition=Q(parent__isnull=True),
                name="ort_name_je_org",
            ),
            models.UniqueConstraint(
                fields=["parent", "name"],
                condition=Q(parent__isnull=False),
                name="raum_name_je_ort",
            ),
        ]

    def __str__(self) -> str:
        return self.full_name

    @property
    def full_name(self) -> str:
        """Name zur Auswahl und in Terminen: „Gebäude, Raum“."""
        return join_name(self.parent.name, self.name) if self.parent_id else self.name

    def effective(self) -> dict:
        """Was ein Termin beim Auswählen übernimmt; Räume erben vom Gebäude."""
        if not self.parent_id:
            return {
                "name": self.name,
                "address": self.address,
                "directions": self.directions,
                "latitude": self.latitude,
                "longitude": self.longitude,
            }
        building = self.parent
        notes = "\n".join(x for x in (building.directions.strip(), self.directions.strip()) if x)
        return {
            "name": self.full_name,
            "address": building.address,
            "directions": notes[:1000],
            "latitude": building.latitude,
            "longitude": building.longitude,
        }


def join_name(building: str, room: str) -> str:
    return f"{building}, {room}"
