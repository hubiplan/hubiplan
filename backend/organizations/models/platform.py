"""Einheiten: Einstellungen der ganzen Instanz."""

from __future__ import annotations

import datetime

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy

from .fields import brand_icon_path
from .organization import DELETION_SHORTEN_GRACE_DAYS


class PlatformSettings(models.Model):
    """Globale Einstellungen der Plattform (genau ein Datensatz)."""

    class PersonData(models.TextChoices):
        SHARED = "shared", gettext_lazy("gemeinsam gepflegt")
        PER_CLUB = "per_club", gettext_lazy("eigene Kopie je Verein")

    person_data_mode = models.CharField(
        "Personendaten bei mehreren Vereinen",
        max_length=10,
        choices=PersonData.choices,
        default=PersonData.SHARED,
    )
    deletion_period_months = models.PositiveSmallIntegerField(
        "Löschfrist nach Austritt (Monate)",
        default=24,
        validators=[MinValueValidator(1), MaxValueValidator(600)],
    )
    # Schutz vor zu frühem Löschen (Fachfrage FQ10): Eine verkürzte Frist gilt erst nach
    # DELETION_SHORTEN_GRACE_DAYS Tagen; bis dahin zählt die vorige, längere Frist.
    deletion_period_previous = models.PositiveSmallIntegerField(
        "vorige Löschfrist (Monate)", null=True, blank=True
    )
    deletion_period_changed_at = models.DateTimeField(
        "Löschfrist verkürzt am", null=True, blank=True
    )
    # Verbund: Einheiten dieser Instanz dürfen sich mit Einheiten auf anderen
    # HUBIplan-Instanzen koppeln. Aus: alles wie bisher auf einer Instanz.
    peering_enabled = models.BooleanField("Kopplung mit anderen Instanzen", default=False)
    peering_allowed_hosts = models.TextField(
        "erlaubte Instanzen (leer = alle)",
        blank=True,
        help_text="Domains, eine je Zeile, z. B. verband.example.org",
    )
    # Verbund Schritt 7: Personen melden sich hier mit ihrem Zugang einer gekoppelten
    # Instanz an (nach eigener Verknüpfung). Aus: nur Zugänge dieser Instanz.
    peering_login = models.BooleanField("Anmeldung über gekoppelte Instanzen", default=False)
    # Gesamtaudit 15.11., MCP-09: Speicher für Webseitenbilder je Einheit (MB, 0 = ohne Grenze)
    website_image_quota_mb = models.PositiveIntegerField(
        "Speicher für Webseitenbilder je Einheit (MB)", default=2048, db_default=2048
    )
    # White Label W2: quadratisches Symbol der Instanz für Browser-Tab und Handy (PWA).
    # Leer: das H-Zeichen von HUBIplan (konzepte/white-label.md)
    brand_icon = models.ImageField(
        "Symbol der Instanz", upload_to=brand_icon_path, blank=True, db_default=""
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Plattform-Einstellungen"
        verbose_name_plural = "Plattform-Einstellungen"

    def __str__(self) -> str:
        return "Plattform-Einstellungen"

    @classmethod
    def load(cls) -> PlatformSettings:
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def shorter_from(self) -> datetime.datetime | None:
        """Ab wann eine verkürzte Löschfrist gilt (None: keine Verkürzung ausstehend)."""
        if self.deletion_period_previous is None or self.deletion_period_changed_at is None:
            return None
        start = self.deletion_period_changed_at + datetime.timedelta(
            days=DELETION_SHORTEN_GRACE_DAYS
        )
        return start if timezone.now() < start else None

    def effective_deletion_months(self) -> int:
        """Die Frist, nach der gerade gelöscht wird: während der Schonfrist die längere."""
        if self.shorter_from() is not None:
            return max(self.deletion_period_months, self.deletion_period_previous or 0)
        return self.deletion_period_months

    def set_deletion_period(self, months: int) -> None:
        """Frist ändern; eine Verkürzung gilt erst nach der Schonfrist (Fachfrage FQ10)."""
        effective = self.effective_deletion_months()
        if months < effective:
            self.deletion_period_previous = effective
            self.deletion_period_changed_at = timezone.now()
        elif months >= effective:
            self.deletion_period_previous = None
            self.deletion_period_changed_at = None
        self.deletion_period_months = months
