"""Einheiten: gemeinsame Felder, Vorgaben und Dateipfade (Erscheinungsbild, Geschäftsjahr)."""

from __future__ import annotations

import datetime

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy

from ..theme import validate_hex_color

MAX_LOGO_BYTES = 2 * 1024 * 1024


def validate_logo(file) -> None:
    if file and file.size > MAX_LOGO_BYTES:
        raise ValidationError(gettext("Das Logo darf höchstens 2 MB groß sein."))


def logo_path(instance, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
    if ext not in {"png", "jpg", "jpeg", "webp"}:
        ext = "png"  # nie eine Endung, die der Webserver als Seite ausliefert
    prefix = "abteilungen" if getattr(instance, "type", "") == "unit" else "organisationen"
    stamp = timezone.now().strftime("%Y%m%d%H%M%S")
    return f"logos/{prefix}/{instance.pk or 'neu'}-{stamp}.{ext}"


def logo_dark_path(instance, filename: str) -> str:
    """Wie ``logo_path``, mit „dunkel“ im Namen, damit beide Logos nie gleich heißen."""
    path = logo_path(instance, filename)
    folder, name = path.rsplit("/", 1)
    return f"{folder}/{name.split('-', 1)[0]}-dunkel-{name.split('-', 1)[1]}"


def brand_icon_path(instance, filename: str) -> str:
    stamp = timezone.now().strftime("%Y%m%d%H%M%S")
    return f"marke/symbol-{stamp}.png"


def homepage_image_path(instance, filename: str) -> str:
    stamp = timezone.now().strftime("%Y%m%d%H%M%S")
    return f"homepages/{instance.pk or 'neu'}-{stamp}.jpg"


def default_jubilee_years() -> list[int]:
    return [10, 25, 40, 50, 60]


def default_unit_jubilee_years() -> list[int]:
    return [10, 25, 50, 60, 75, 100, 125, 150, 175, 200]


class DatePrecision(models.TextChoices):
    """Wie genau Mitgliedschaften angezeigt und Jubiläen berechnet werden.

    Gespeichert wird immer tagesgenau; die Genauigkeit wirkt nur auf Anzeige
    und Berechnung.
    """

    DAY = "day", gettext_lazy("tagesgenau")
    MONTH = "month", gettext_lazy("monatsgenau")
    YEAR = "year", gettext_lazy("jahresgenau")


def founding_year_validators():
    return [MinValueValidator(800), MaxValueValidator(2100)]


SHORT_NAME_MAX = 50


# Arbeitsbereich einer Untereinheit: diese Module sind immer eingeschaltet
WORKSPACE_MODULES = frozenset({"finance", "billing"})


# Vorgabe für die Bezeichnung neuer Einheiten (Einzahl, Mehrzahl, Genus, Genitiv);
# jede Einheit kann sie in der App ändern.
DEFAULT_LABELS = {
    "platform": ("Plattform", "Plattformen", "f", ""),
    "federation": ("Dachverband", "Dachverbände", "m", "Dachverbands"),
    "club": ("Verein", "Vereine", "m", "Vereins"),
}


# Vorgabe für die Bezeichnung der Untereinheiten (``department_label*``)
DEFAULT_CHILD_LABELS = {
    "platform": ("Einheit", "Einheiten", "f", ""),
    "federation": ("Verein", "Vereine", "m", "Vereins"),
    "unit": ("Gruppe", "Gruppen", "f", ""),
}


class ShortNameMixin:
    """Optionaler Kurzname für enge Stellen (Navigation, Listen, Auswahlfelder).

    Dokumente (Rechnungen, PDFs, Ausweise, Mails) verwenden immer den
    vollständigen Namen ``name``.
    """

    @property
    def display_name(self) -> str:
        return self.short_name or self.name


class ThemeFields(models.Model):
    """Erscheinungsbild: leer bedeutet „von der übergeordneten Ebene erben“."""

    primary_color = models.CharField(
        "Primärfarbe", max_length=7, blank=True, validators=[validate_hex_color]
    )
    accent_color = models.CharField(
        "Akzentfarbe", max_length=7, blank=True, validators=[validate_hex_color]
    )
    # Namen und weitere Farben der Palette (Ralf 2026-10-31, bis sechs Farben)
    primary_color_name = models.CharField("Name der Hauptfarbe", max_length=30, blank=True)
    accent_color_name = models.CharField("Name der Zweitfarbe", max_length=30, blank=True)
    extra_colors = models.JSONField("weitere Farben", default=list, blank=True)
    # Wofür Haupt- und Zweitfarbe da sind (Farbblatt, Ralf 10.11.2026); weitere Farben
    # tragen das in extra_colors[].use
    primary_color_use = models.CharField(
        "Verwendung der Hauptfarbe", max_length=60, blank=True, db_default=""
    )
    accent_color_use = models.CharField(
        "Verwendung der Zweitfarbe", max_length=60, blank=True, db_default=""
    )
    # Bis zu zwei benannte Verläufe aus Palettenplätzen (Ralf 10.11.2026):
    # [{name, from, to, direction}]
    gradients = models.JSONField("Verläufe", default=list, blank=True, db_default=[])
    # Wofür eine Palettenfarbe da ist (Ralf 13.11.2026): {rolle: platz} mit den Rollen
    # text, muted, surface, background (theme.PALETTE_ROLES); Webseite › Gestaltung nimmt sie
    # als Vorgabe, mit palette_roles_in_app auch die HUBIplan-Oberfläche im hellen Modus
    palette_roles = models.JSONField("Farbrollen", default=dict, blank=True, db_default={})
    palette_roles_in_app = models.BooleanField(
        "Farbrollen auch in HUBIplan", default=False, db_default=False
    )
    logo = models.ImageField(
        "Logo/Wappen", upload_to=logo_path, blank=True, validators=[validate_logo]
    )
    # Zweites Logo für den Dunkelmodus (Ralf 10.11.2026). Leer: das helle Logo gilt auch dunkel
    logo_dark = models.ImageField(
        "Logo/Wappen für den Dunkelmodus",
        upload_to=logo_dark_path,
        blank=True,
        # Rückweg: der Stand davor legt Einheiten ohne diese Spalte an
        db_default="",
        validators=[validate_logo],
    )
    # Quadratisches Symbol für Browser-Tab und Handy, wenn die Einheit eine eigene Adresse
    # hat (White Label W7). Leer: Wappen quadratisch, sonst Symbol der Instanz
    brand_icon = models.ImageField("Symbol", upload_to=brand_icon_path, blank=True, db_default="")

    class Meta:
        abstract = True


class FiscalYearFields(models.Model):
    """Geschäftsjahr: Beginn als Tag und Monat, es dauert immer zwölf Monate.

    Ein Geschäftsjahr heißt nach dem Kalenderjahr, in dem es beginnt. Beginnt es
    nicht am 1. Januar, wird es als „2025/26“ angezeigt.
    """

    fiscal_start_month = models.PositiveSmallIntegerField(
        "Geschäftsjahr beginnt im Monat",
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )
    fiscal_start_day = models.PositiveSmallIntegerField(
        "Geschäftsjahr beginnt am Tag",
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
    )

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        try:
            datetime.date(2001, self.fiscal_start_month, self.fiscal_start_day)
        except ValueError as exc:
            raise ValidationError(
                {
                    "fiscal_start_day": gettext(
                        "Diesen Tag gibt es in dem Monat nicht (in jedem Jahr)."
                    )
                }
            ) from exc

    @property
    def fiscal_is_calendar(self) -> bool:
        return self.fiscal_start_month == 1 and self.fiscal_start_day == 1

    def fiscal_start(self, year: int) -> datetime.date:
        return datetime.date(year, self.fiscal_start_month, self.fiscal_start_day)

    def fiscal_range(self, year: int) -> tuple[datetime.date, datetime.date]:
        """Erster Tag und letzter Tag des Geschäftsjahres ``year``."""
        start = self.fiscal_start(year)
        end = self.fiscal_start(year + 1) - datetime.timedelta(days=1)
        return start, end

    def fiscal_year_of(self, day: datetime.date) -> int:
        return day.year if day >= self.fiscal_start(day.year) else day.year - 1

    def fiscal_label(self, year: int) -> str:
        if self.fiscal_is_calendar:
            return str(year)
        return f"{year}/{(year + 1) % 100:02d}"
