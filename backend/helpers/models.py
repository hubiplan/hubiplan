"""Helferdienste und Schichtpläne (konzepte/helferdienste.md).

Ein Dienstplan (``HelperPlan``) gehört zu einem Anlass, z. B. dem Schützenfest. Er hat
Dienste (Theke, Kasse, Aufbau), jeder Dienst Schichten mit Bedarf, und in jede Schicht
werden Personen eingeteilt: Mitglieder oder Externe mit Name und Telefon. Pläne gehören zu
einem Verein oder einer Untereinheit (Spalte ``department``, wie bei den Versammlungen).
"""

from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.encfields import EncryptedCharField, EncryptedTextField


class HelperPlan(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("in Vorbereitung")
        PUBLISHED = "published", _("veröffentlicht")
        CLOSED = "closed", _("abgeschlossen")

    class Signup(models.TextChoices):
        SELF = "self", _("Mitglieder tragen sich selbst ein")
        ASSIGN = "assign", _("nur Einteilung")

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    department = models.ForeignKey(
        "organizations.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    title = models.CharField(_("Titel"), max_length=200)
    event = models.ForeignKey(
        "events.Event", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    signup = models.CharField(max_length=10, choices=Signup.choices, default=Signup.SELF)
    cancel_days = models.PositiveSmallIntegerField(default=2, validators=[MaxValueValidator(60)])
    max_shifts = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(50)]
    )
    show_names = models.BooleanField(default=True)
    # Erinnerung per Mail so viele Tage vor der Schicht (leer: keine)
    remind_days = models.PositiveSmallIntegerField(
        null=True, blank=True, default=1, validators=[MaxValueValidator(14)]
    )
    note = EncryptedTextField(_("Hinweis"), blank=True)
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["organization", "department"])]

    def __str__(self):
        return self.title


class Duty(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    plan = models.ForeignKey(HelperPlan, on_delete=models.CASCADE, related_name="duties")
    name = models.CharField(_("Dienst"), max_length=100)
    description = models.CharField(_("Beschreibung"), max_length=500, blank=True)
    location = models.CharField(_("Ort"), max_length=200, blank=True)
    min_age = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(99)]
    )
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self):
        return self.name


class Shift(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    duty = models.ForeignKey(Duty, on_delete=models.CASCADE, related_name="shifts")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    needed = models.PositiveSmallIntegerField(default=1, validators=[MaxValueValidator(500)])
    note = models.CharField(_("Hinweis"), max_length=200, blank=True)

    class Meta:
        ordering = ["starts_at", "pk"]

    def __str__(self):
        return f"shift {self.pk}"


class ShiftQuota(models.Model):
    """Kontingent: Teil des Bedarfs einer Schicht, den eine Untereinheit füllt (Schritt H3)."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name="quotas")
    department = models.ForeignKey(
        "organizations.Department", on_delete=models.CASCADE, related_name="+"
    )
    count = models.PositiveSmallIntegerField(validators=[MaxValueValidator(500)])

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(fields=["shift", "department"], name="quota_once_per_unit")
        ]

    def __str__(self):
        return f"quota {self.pk}"


class ShiftAssignment(models.Model):
    """Eine Person in einer Schicht. Externe nur mit Name und Telefon (verschlüsselt)."""

    class Origin(models.TextChoices):
        SELF = "self", _("selbst eingetragen")
        ASSIGNED = "assigned", _("eingeteilt")
        UNIT = "unit", _("von der Untereinheit eingeteilt")

    class Status(models.TextChoices):
        ACTIVE = "active", _("eingetragen")
        CANCELLED = "cancelled", _("abgesagt")

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name="assignments")
    membership = models.ForeignKey(
        "members.Membership", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    quota = models.ForeignKey(
        ShiftQuota, null=True, blank=True, on_delete=models.SET_NULL, related_name="assignments"
    )
    name = EncryptedCharField(_("Name"), max_length=200)
    phone = EncryptedCharField(_("Telefon"), max_length=50, blank=True)
    origin = models.CharField(max_length=10, choices=Origin.choices, default=Origin.ASSIGNED)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    done = models.BooleanField(null=True, blank=True)
    reminded_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["shift", "membership"],
                condition=models.Q(membership__isnull=False, status="active"),
                name="assignment_once_per_member",
            )
        ]

    def __str__(self):
        return f"assignment {self.pk}"
