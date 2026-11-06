"""Buchungskalender für Infrastruktur und Material (konzepte/infrastruktur.md, Abschnitt 4).

Eine Buchung belegt ein Objekt des Bestands (``materials.MaterialItem``) verbindlich,
einmalig oder als Serie. Die einzelnen Belegungen stehen ausgerechnet in ``BookingSlot``;
eine Ausschlussbedingung der Datenbank verhindert, dass sich zwei bestätigte Belegungen
desselben Objekts überschneiden, auch bei gleichzeitigen Anfragen. Wird ein ganzes Gebäude
gebucht, erhält auch jeder seiner Bereiche eine Belegung; so kollidiert es mit jeder
Buchung eines Bereichs, zwei verschiedene Bereiche aber nicht miteinander.
"""

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from core.encfields import EncryptedCharField, EncryptedJSONField, EncryptedTextField


class Booking(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", _("angefragt")
        CONFIRMED = "confirmed", _("bestätigt")
        REJECTED = "rejected", _("abgelehnt")
        CANCELLED = "cancelled", _("storniert")

    class Visibility(models.TextChoices):
        PUBLIC = "public", _("öffentlich")
        MEMBERS = "members", _("Mitglieder")
        BOARD = "board", _("nur Verwalter")

    class Repeat(models.TextChoices):
        NONE = "none", _("einmalig")
        WEEKLY = "weekly", _("wöchentlich")
        MONTHLY = "monthly", _("monatlich")
        YEARLY = "yearly", _("jährlich")

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    # Datenbereich des Objekts (Verein oder Untereinheit), wie beim Material
    department = models.ForeignKey(
        "organizations.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    item = models.ForeignKey(
        "materials.MaterialItem", on_delete=models.CASCADE, related_name="bookings"
    )
    title = EncryptedCharField(_("Zweck"), max_length=200)
    note = EncryptedTextField(_("Notiz"), blank=True)
    starts_at = models.DateTimeField(_("Beginn"))
    ends_at = models.DateTimeField(_("Ende"))
    all_day = models.BooleanField(default=False)
    repeat = models.CharField(max_length=10, choices=Repeat.choices, default=Repeat.NONE)
    repeat_interval = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(52)]
    )
    repeat_until = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED)
    visibility = models.CharField(
        max_length=10, choices=Visibility.choices, default=Visibility.MEMBERS
    )
    # Externe (z. B. Saalmiete): Name, E-Mail, Telefon; nur für Verwalter sichtbar
    contact = EncryptedJSONField(default=dict, blank=True)
    event = models.ForeignKey(
        "events.Event", null=True, blank=True, on_delete=models.SET_NULL, related_name="bookings"
    )
    competition = models.ForeignKey(
        "competitions.Competition",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bookings",
    )
    # Termin oder Wettbewerb hat sich geändert und die neue Zeit war nicht frei
    needs_review = models.BooleanField(default=False)
    booked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["starts_at", "pk"]
        indexes = [models.Index(fields=["organization", "department", "item"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")), name="booking_end_after_start"
            )
        ]

    def __str__(self):
        return f"Buchung {self.pk}"

    @property
    def is_series(self) -> bool:
        return self.repeat != self.Repeat.NONE


class BookingException(models.Model):
    """Ein einzelnes Vorkommen einer Serienbuchung fällt aus."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="exceptions")
    original_start = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "original_start"], name="booking_exception_once"
            )
        ]

    def __str__(self):
        return f"Ausfall {self.original_start:%Y-%m-%d %H:%M}"


class BookingSlot(models.Model):
    """Ausgerechnete Belegung eines Objekts (inkl. Rüstzeiten) für Konflikte und Ansichten."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="slots")
    resource = models.ForeignKey(
        "materials.MaterialItem", on_delete=models.CASCADE, related_name="booking_slots"
    )
    original_start = models.DateTimeField()
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    period = DateTimeRangeField()
    confirmed = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["resource", "starts_at"])]
        constraints = [
            ExclusionConstraint(
                name="booking_slot_no_overlap",
                expressions=[
                    ("resource", RangeOperators.EQUAL),
                    ("period", RangeOperators.OVERLAPS),
                ],
                condition=Q(confirmed=True),
            )
        ]

    def __str__(self):
        return f"Belegung {self.starts_at:%Y-%m-%d %H:%M}"
