"""Kasse: Jahresabschluss und Wiedereröffnung."""

from __future__ import annotations

from django.conf import settings
from django.db import models

from core.encfields import EncryptedCharField


class YearClosing(models.Model):
    """Jahresabschluss: danach ist das Geschäftsjahr für Buchungen gesperrt."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    year = models.PositiveSmallIntegerField("Geschäftsjahr")
    closed_at = models.DateTimeField(auto_now_add=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Stand beim Abschluss (Bestände und Summen), zum Nachweis
    snapshot = models.JSONField(default=dict, blank=True)
    # Ende der Aufbewahrungsfrist (Finanzamt-Prüfung C6, finance/retention.py)
    documents_purged_at = models.DateTimeField("Belege gelöscht am", null=True, blank=True)
    records_purged_at = models.DateTimeField("Bücher anonymisiert am", null=True, blank=True)
    purged_by_name = EncryptedCharField(
        "bereinigt von", max_length=200, blank=True, db_default="", strict=True
    )
    # Löschsperre (Fachfrage FQ10): z. B. laufende Prüfung oder Rechtsstreit. Solange ein
    # Grund eingetragen ist, wird nichts gelöscht, auch nach Ablauf der Frist.
    retention_hold = models.CharField(
        "Löschsperre (Grund)", max_length=500, blank=True, db_default=""
    )
    retention_hold_by_name = EncryptedCharField(
        "Löschsperre gesetzt von", max_length=200, blank=True, db_default="", strict=True
    )
    retention_hold_at = models.DateTimeField("Löschsperre gesetzt am", null=True, blank=True)
    # Antrag auf Aufheben, wenn der Verein das Vier-Augen-Prinzip eingeschaltet hat: Die Kasse
    # beantragt mit Grund, eine andere Person mit Rollenverwaltung bestätigt.
    reopen_requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reopen_requested_by_name = EncryptedCharField(
        "Aufheben beantragt von", max_length=200, blank=True, db_default="", strict=True
    )
    reopen_requested_at = models.DateTimeField("Aufheben beantragt am", null=True, blank=True)
    reopen_reason = models.CharField(
        "Grund für das Aufheben", max_length=500, blank=True, db_default=""
    )

    class Meta:
        verbose_name = "Jahresabschluss"
        verbose_name_plural = "Jahresabschlüsse"
        ordering = ["-year"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "year"], name="abschluss_eindeutig")
        ]

    def __str__(self) -> str:
        return f"Abschluss {self.year}"


class ReopenedClosing(models.Model):
    """Aufgehobener Jahresabschluss: alter Stand mit Grund, zum Nachweis (GoBD, B4)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    year = models.PositiveSmallIntegerField("Geschäftsjahr")
    closed_at = models.DateTimeField("abgeschlossen am")
    closed_by_name = EncryptedCharField(
        "abgeschlossen von", max_length=200, blank=True, strict=True
    )
    snapshot = models.JSONField(default=dict, blank=True)
    reopened_at = models.DateTimeField("aufgehoben am", auto_now_add=True)
    reopened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reopened_by_name = EncryptedCharField("aufgehoben von", max_length=200, blank=True, strict=True)
    reason = models.CharField("Grund", max_length=500)

    class Meta:
        verbose_name = "aufgehobener Jahresabschluss"
        verbose_name_plural = "aufgehobene Jahresabschlüsse"
        ordering = ["-year", "-reopened_at"]
        indexes = [models.Index(fields=["organization", "year"])]

    def __str__(self) -> str:
        return f"Abschluss {self.year}, aufgehoben"
