"""Kasse: Projekte und Projektreihen."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext, gettext_lazy


class ProjectSeries(models.Model):
    """Reihe wiederkehrender Veranstaltungen (z. B. das jährliche Schützenfest),
    um die Jahre miteinander zu vergleichen."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    name = models.CharField("Name", max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Veranstaltungsreihe"
        verbose_name_plural = "Veranstaltungsreihen"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "name"], name="reihe_name_eindeutig")
        ]

    def __str__(self) -> str:
        return self.name


class Project(models.Model):
    """Veranstaltung: bündelt Einnahmen und Ausgaben für eine eigene Auswertung.

    Die Buchungen bleiben normale Buchungen im Kassenbuch. Termine im Kalender
    können auf die Veranstaltung verweisen (``events.Event.project``), müssen es
    aber nicht.
    """

    class Status(models.TextChoices):
        PLANNED = "planned", gettext_lazy("geplant")
        RUNNING = "running", gettext_lazy("laufend")
        DONE = "done", gettext_lazy("abgeschlossen")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    # Leer: Veranstaltung der Organisation selbst, sonst einer Abteilung
    department = models.ForeignKey(
        "organizations.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Abteilung",
    )
    series = models.ForeignKey(
        ProjectSeries,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projects",
        verbose_name="Reihe",
    )
    name = models.CharField("Name", max_length=200)
    starts_on = models.DateField("Beginn")
    ends_on = models.DateField("Ende", null=True, blank=True)
    description = models.TextField("Beschreibung", blank=True, max_length=5000)
    status = models.CharField(
        "Status", max_length=10, choices=Status.choices, default=Status.PLANNED
    )
    # Planwerte (Haushaltsplan): leer, wenn nichts geplant ist
    plan_income = models.DecimalField(
        "geplante Einnahmen", max_digits=12, decimal_places=2, null=True, blank=True
    )
    plan_expense = models.DecimalField(
        "geplante Ausgaben", max_digits=12, decimal_places=2, null=True, blank=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Veranstaltung"
        verbose_name_plural = "Veranstaltungen"
        ordering = ["-starts_on", "name"]
        indexes = [models.Index(fields=["organization", "starts_on"])]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        errors: dict[str, str] = {}
        if self.ends_on and self.starts_on and self.ends_on < self.starts_on:
            errors["ends_on"] = gettext("Das Ende liegt vor dem Beginn.")
        if self.organization_id:
            if self.series_id and self.series.organization_id != self.organization_id:
                errors["series"] = gettext("Unbekannte Reihe.")
            if self.department_id and self.department.organization_id != self.organization_id:
                from organizations.terms import fill

                errors["department"] = fill("Unbekannt{adj} {sg}.", self.organization)
        if errors:
            raise ValidationError(errors)
