"""Kasse: Kassensturz und Kassenprüfung."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy

from core.encfields import EncryptedCharField
from core.privatefiles import PrivateFileField
from exchange.models import private_storage

from .base import Account
from .bookings import Booking


def cash_count_path(instance, filename: str) -> str:
    stamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
    return f"zaehlungen/{instance.organization_id}/{stamp}.pdf"


# Stückelung in Cent: Scheine und Münzen (Euro)
DENOMINATIONS = [50000, 20000, 10000, 5000, 2000, 1000, 500, 200, 100, 50, 20, 10, 5, 2, 1]


class CashCount(models.Model):
    """Zählprotokoll einer Barkasse oder Kassenbericht eines Festes (Finanzamt-Prüfung B2).

    Wird einmal erstellt und danach nicht mehr geändert; die zugehörigen Buchungen
    (Kassendifferenz bzw. Tageseinnahmen) tragen das PDF als Beleg."""

    class Kind(models.TextChoices):
        COUNT = "count", gettext_lazy("Zählprotokoll")
        EVENT = "event", gettext_lazy("Kassenbericht")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    kind = models.CharField("Art", max_length=10, choices=Kind.choices)
    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="cash_counts", verbose_name="Barkasse"
    )
    date = models.DateField("Datum")
    title = models.CharField("Bezeichnung", max_length=200, blank=True)
    project = models.ForeignKey(
        "Project", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    # Anzahl je Stückelung, Schlüssel in Cent als Text
    denominations = models.JSONField("Stückelung", default=dict, blank=True)
    counted = models.DecimalField("gezählt", max_digits=12, decimal_places=2)
    # Zählprotokoll: Bestand laut Kassenbuch am Ende des Tages vor der Differenzbuchung
    expected = models.DecimalField("Soll laut Kassenbuch", max_digits=12, decimal_places=2)
    # Kassenbericht: Wechselgeld zu Beginn, bar bezahlte Ausgaben, Entnahmen während des Festes
    opening = models.DecimalField("Anfangsbestand", max_digits=12, decimal_places=2, default=0)
    expenses = models.DecimalField(
        "Ausgaben aus der Kasse", max_digits=12, decimal_places=2, default=0
    )
    withdrawals = models.DecimalField("Entnahmen", max_digits=12, decimal_places=2, default=0)
    # Kassenbericht: Aufteilung der Einnahmen [{category, name, amount}]
    lines = models.JSONField("Aufteilung", default=list, blank=True)
    note = models.CharField("Bemerkung/Grund", max_length=500, blank=True)
    counted_by = EncryptedCharField("gezählt von", max_length=200, strict=True)
    witness = EncryptedCharField("zweite Person", max_length=200, blank=True, strict=True)
    booking_ids = models.JSONField("Buchungen", default=list, blank=True)
    pdf = PrivateFileField("PDF", storage=private_storage, upload_to=cash_count_path, blank=True)
    pdf_sha256 = models.CharField("Prüfsumme", max_length=64, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Kassenzählung"
        verbose_name_plural = "Kassenzählungen"
        ordering = ["-date", "-pk"]
        indexes = [models.Index(fields=["organization", "date"])]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.date:%d.%m.%Y}"

    @property
    def difference(self) -> Decimal:
        return self.counted - self.expected

    @property
    def takings(self) -> Decimal:
        """Kassenbericht: Tageseinnahme = Endbestand − Anfangsbestand + Ausgaben + Entnahmen."""
        return self.counted - self.opening + self.expenses + self.withdrawals


class CashAudit(models.Model):
    """Kassenprüfung eines Geschäftsjahres (Konzept vereinskasse-steuern, S6).

    Die Kasse legt den Prüfauftrag an; die Kassenprüfer (Rolle mit Kasse lesen, ohne Kasse
    führen) haken Stichproben und Kontenstände ab, halten Feststellungen fest und geben eine
    Empfehlung zur Entlastung. Daraus entsteht der Prüfbericht als PDF."""

    class Status(models.TextChoices):
        OPEN = "open", gettext_lazy("in Prüfung")
        DONE = "done", gettext_lazy("abgeschlossen")

    class Recommendation(models.TextChoices):
        NONE = "", gettext_lazy("noch offen")
        DISCHARGE = "discharge", gettext_lazy("Entlastung empfohlen")
        NOTES = "notes", gettext_lazy("Entlastung mit Anmerkungen empfohlen")
        REFUSE = "refuse", gettext_lazy("Entlastung nicht empfohlen")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    year = models.PositiveSmallIntegerField("Geschäftsjahr")
    auditors = models.CharField("Kassenprüfer", max_length=300, blank=True)
    due_on = models.DateField("zu prüfen bis", null=True, blank=True)
    sample_size = models.PositiveSmallIntegerField("Stichproben", default=20)
    # Prüfpunkte: {key: {"ok": true|false|null, "note": "…"}} (Schlüssel in finance/cash_audit.py)
    checks = models.JSONField("Prüfpunkte", default=dict, blank=True)
    findings = models.TextField("Feststellungen", max_length=5000, blank=True)
    recommendation = models.CharField(
        "Empfehlung", max_length=10, choices=Recommendation.choices, blank=True, default=""
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    meeting = models.ForeignKey(
        "meetings.Meeting",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Versammlung",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField("abgeschlossen am", null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "Kassenprüfung"
        verbose_name_plural = "Kassenprüfungen"
        ordering = ["-year"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "year"], name="kassenpruefung_je_jahr")
        ]

    def __str__(self) -> str:
        return f"Kassenprüfung {self.year}"

    def clean(self):
        if self.sample_size is not None and not 1 <= self.sample_size <= 200:
            raise ValidationError({"sample_size": gettext("Bitte 1 bis 200 Stichproben angeben.")})


class CashAuditSample(models.Model):
    """Stichprobe einer Kassenprüfung: eine Buchung, die die Prüfer mit dem Beleg vergleichen."""

    class Result(models.TextChoices):
        OPEN = "", gettext_lazy("offen")
        OK = "ok", gettext_lazy("in Ordnung")
        ISSUE = "issue", gettext_lazy("Rückfrage")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    audit = models.ForeignKey(CashAudit, on_delete=models.CASCADE, related_name="samples")
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="+")
    result = models.CharField(max_length=10, choices=Result.choices, blank=True, default="")
    note = models.CharField("Anmerkung", max_length=300, blank=True)
    checked_by_name = models.CharField(max_length=200, blank=True)
    checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["booking__date", "booking__number", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["audit", "booking"], name="stichprobe_einmal")
        ]

    def __str__(self) -> str:
        return f"Stichprobe {self.booking_id}"


class CashAuditAccount(models.Model):
    """Kontenabgleich einer Kassenprüfung: Bestand laut Kassenbuch gegen Kontoauszug bzw.
    Zählung am Ende des Geschäftsjahres."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    audit = models.ForeignKey(CashAudit, on_delete=models.CASCADE, related_name="accounts")
    # PROTECT: Eine Kassenprüfung verliert ihre Konten nicht mit dem Konto (B-M05)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="+")
    statement_balance = models.DecimalField(
        "Stand laut Kontoauszug bzw. Zählung",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    note = models.CharField("Anmerkung", max_length=300, blank=True)
    checked_by_name = models.CharField(max_length=200, blank=True)
    checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["account__position", "account__name", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["audit", "account"], name="kontenabgleich_einmal")
        ]

    def __str__(self) -> str:
        return f"Kontenabgleich {self.account_id}"
