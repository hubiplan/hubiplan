"""Qualifikationen und Nachweise mit Ablaufdatum (konzepte/funktionsvorschlaege-2026-11-12.md, 4).

Jede Einheit legt ihre Arten selbst an (z. B. Erste Hilfe, Standaufsicht, Jugendleiter,
Übungsleiter, Sachkunde, Einsicht ins erweiterte Führungszeugnis); nichts ist vorgegeben.
Am Mitglied steht je Nachweis, seit wann er gilt und bis wann. Eine Verlängerung ist ein
neuer Eintrag, der alte bleibt im Verlauf.

Arten mit „nur Einsichtsvermerk“ (Führungszeugnis) halten nur fest, dass und wann der
Nachweis eingesehen wurde: keine Bemerkung, kein Dokument, nie der Inhalt.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class QualificationType(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    name = models.CharField(_("Bezeichnung"), max_length=100)
    description = models.CharField(_("Beschreibung"), max_length=300, blank=True)
    # Übliche Gültigkeit: schlägt beim Eintragen das Ablaufdatum vor (leer: unbefristet)
    validity_months = models.PositiveSmallIntegerField(
        _("gültig für Monate"), null=True, blank=True, validators=[MaxValueValidator(600)]
    )
    # Erinnerung so viele Tage vor dem Ablauf (leer: keine Erinnerung)
    remind_days = models.PositiveSmallIntegerField(
        _("Erinnerung Tage vorher"),
        null=True,
        blank=True,
        default=60,
        validators=[MaxValueValidator(365)],
    )
    # Nur Vermerk über die Einsicht (z. B. Führungszeugnis): keine Bemerkung
    inspection_only = models.BooleanField(_("nur Einsichtsvermerk"), default=False)
    is_archived = models.BooleanField(_("nicht mehr verwendet"), default=False)
    sort_order = models.PositiveSmallIntegerField(_("Reihenfolge"), default=0)

    class Meta:
        verbose_name = _("Qualifikationsart")
        verbose_name_plural = _("Qualifikationsarten")
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"], name="qualifikationsart_je_organisation"
            )
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        from core.reorder import append_if_new

        append_if_new(
            self,
            "sort_order",
            QualificationType.objects.filter(organization_id=self.organization_id),
        )
        super().save(*args, **kwargs)


class Qualification(models.Model):
    """Nachweis einer Person: erworben (bzw. eingesehen) am, gültig bis."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    person = models.ForeignKey(
        "members.Person", on_delete=models.CASCADE, related_name="qualifications"
    )
    kind = models.ForeignKey(
        QualificationType,
        on_delete=models.PROTECT,
        related_name="records",
        verbose_name=_("Qualifikation"),
    )
    acquired_on = models.DateField(_("erworben am"))
    valid_until = models.DateField(_("gültig bis"), null=True, blank=True)
    note = models.CharField(_("Bemerkung"), max_length=200, blank=True)
    # Erinnerung verschickt (zurückgesetzt, wenn sich das Ablaufdatum ändert)
    reminded_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Qualifikation")
        verbose_name_plural = _("Qualifikationen")
        ordering = ["-acquired_on", "-pk"]
        indexes = [
            models.Index(fields=["organization", "person"]),
            models.Index(fields=["organization", "valid_until"]),
        ]

    def __str__(self) -> str:
        return f"{self.kind}"
