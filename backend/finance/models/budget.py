"""Kasse: Haushaltsplan."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy

from .base import Category


class Budget(models.Model):
    """Haushaltsplan eines Geschäftsjahres: geplante Einnahmen und Ausgaben je Kategorie.

    Die Buchungen bleiben, wie sie sind; der Plan liefert nur den Vergleichswert. Ein
    beschlossener Plan ist gesperrt, bis er wieder auf Entwurf gesetzt wird."""

    class Status(models.TextChoices):
        DRAFT = "draft", gettext_lazy("Entwurf")
        ADOPTED = "adopted", gettext_lazy("beschlossen")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    year = models.PositiveSmallIntegerField("Geschäftsjahr")
    status = models.CharField("Stand", max_length=10, choices=Status.choices, default=Status.DRAFT)
    adopted_on = models.DateField("beschlossen am", null=True, blank=True)
    adopted_by = models.CharField("beschlossen durch", max_length=200, blank=True)
    note = models.TextField("Bemerkung", max_length=2000, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Haushaltsplan"
        verbose_name_plural = "Haushaltspläne"
        ordering = ["-year"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "year"], name="haushaltsplan_eindeutig")
        ]

    def __str__(self) -> str:
        return f"Haushaltsplan {self.year}"


class BudgetLine(models.Model):
    """Planbetrag für eine Kategorie, auf Wunsch nur für eine Untereinheit.

    Eine Zeile ohne Untereinheit zählt alle Buchungen der Kategorie, die keine eigene Zeile
    ihrer Untereinheit haben."""

    class Kind(models.TextChoices):
        INCOME = "income", gettext_lazy("Einnahmen")
        EXPENSE = "expense", gettext_lazy("Ausgaben")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="lines")
    kind = models.CharField("Art", max_length=10, choices=Kind.choices)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="budget_lines", verbose_name="Kategorie"
    )
    department = models.ForeignKey(
        "organizations.Department",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Abteilung",
    )
    amount = models.DecimalField("Planbetrag", max_digits=12, decimal_places=2)
    note = models.CharField("Bemerkung", max_length=200, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Zeile im Haushaltsplan"
        verbose_name_plural = "Zeilen im Haushaltsplan"
        ordering = ["position", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["budget", "kind", "category", "department"],
                name="haushaltsplan_zeile_eindeutig",
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gte=0), name="haushaltsplan_betrag_nicht_negativ"
            ),
        ]

    def __str__(self) -> str:
        return f"Planzeile {self.pk}"
