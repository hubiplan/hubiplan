"""Kasse: Kontoauszüge und Bankanbindung."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy

from core.encfields import EncryptedCharField, EncryptedJSONField, EncryptedTextField
from core.privatefiles import PrivateFileField
from exchange.models import private_storage

from .base import Account
from .bookings import Booking


def bank_statement_path(instance, filename: str) -> str:
    stamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
    return f"kontoauszuege/{instance.organization_id}/{stamp}-{filename}"


class BankStatement(models.Model):
    """Ein eingelesener Kontoauszug (eine Datei kann mehrere enthalten)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="statements")
    file_name = models.CharField("Datei", max_length=200)
    reference = models.CharField("Auszug", max_length=100, blank=True)
    date_from = models.DateField("von", null=True, blank=True)
    date_to = models.DateField("bis", null=True, blank=True)
    opening_balance = models.DecimalField(
        "Anfangssaldo", max_digits=12, decimal_places=2, null=True, blank=True
    )
    closing_balance = models.DecimalField(
        "Endsaldo", max_digits=12, decimal_places=2, null=True, blank=True
    )
    line_count = models.PositiveIntegerField("Umsätze", default=0)
    duplicate_count = models.PositiveIntegerField("schon eingelesen", default=0)
    # Die eingelesene Datei unverändert (GoBD: elektronische Kontoauszüge im Original)
    source = PrivateFileField(
        "Originaldatei", storage=private_storage, upload_to=bank_statement_path, blank=True
    )
    source_sha256 = models.CharField(max_length=64, blank=True)
    # Herkunft: leer = hochgeladene Datei, sonst der Bankweg des Abrufs (z. B. „fints“)
    channel = models.CharField("Abruf über", max_length=10, blank=True, default="", db_default="")
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Kontoauszug"
        verbose_name_plural = "Kontoauszüge"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Kontoauszug {self.reference or self.pk} ({self.account_id})"


class BankLine(models.Model):
    """Ein Umsatz aus dem Kontoauszug; wird zugeordnet, gebucht oder übergangen."""

    class Status(models.TextChoices):
        OPEN = "open", gettext_lazy("offen")
        DONE = "done", gettext_lazy("erledigt")
        IGNORED = "ignored", gettext_lazy("übergangen")

    class Suggestion(models.TextChoices):
        NONE = "", gettext_lazy("kein Vorschlag")
        INVOICE = "invoice", gettext_lazy("Zahlung zu Rechnung")
        DEBIT_RUN = "debit_run", gettext_lazy("Lastschriftlauf")
        BOOKED = "booked", gettext_lazy("schon im Kassenbuch")
        RETURN = "return", gettext_lazy("Rücklastschrift")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    statement = models.ForeignKey(BankStatement, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="+")
    date = models.DateField("Buchungstag")
    value_date = models.DateField("Wertstellung", null=True, blank=True)
    amount = models.DecimalField("Betrag", max_digits=12, decimal_places=2)
    credit = models.BooleanField("Gutschrift")
    name = EncryptedCharField("Gegenseite", max_length=200, blank=True, strict=True)
    iban = EncryptedCharField("IBAN der Gegenseite", max_length=34, blank=True)
    partner = models.ForeignKey(
        "billing.BusinessPartner",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Geschäftspartner",
    )
    purpose = models.CharField("Verwendungszweck", max_length=500, blank=True)
    end_to_end = models.CharField("End-to-End-Referenz", max_length=35, blank=True)
    bank_ref = models.CharField("Bankreferenz", max_length=100, blank=True)
    return_code = models.CharField("Rückgabegrund", max_length=10, blank=True)
    batch_count = models.PositiveIntegerField("Einzelposten", default=1)
    # Einzelposten einer Sammelbuchung, so wie sie im Auszug stehen (Audit 31.10. FIN31-02)
    details = EncryptedJSONField(
        "Einzelposten der Sammelbuchung", default=list, blank=True, strict=True
    )
    fingerprint = models.CharField(max_length=64)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    suggestion = models.CharField(
        max_length=10, choices=Suggestion.choices, blank=True, default=Suggestion.NONE
    )
    # Vorschlag beruht auf einer Referenz (Rechnungsnummer, Name, Mandat) und darf mit
    # „Alle Vorschläge übernehmen“ gebucht werden; sonst nur einzeln nach Prüfung (FIN31-03)
    suggestion_sure = models.BooleanField("Vorschlag sicher", default=False)
    suggested_invoice = models.ForeignKey(
        "billing.Invoice", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    suggested_run = models.ForeignKey(
        "billing.DebitRun", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    suggested_booking = models.ForeignKey(
        Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    suggested_membership = models.ForeignKey(
        "members.Membership", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    booking = models.ForeignKey(
        Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name="bank_lines"
    )
    done_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    done_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Kontoumsatz"
        verbose_name_plural = "Kontoumsätze"
        ordering = ["date", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "account", "fingerprint"], name="kontoumsatz_einmal"
            )
        ]

    def __str__(self) -> str:
        sign = "+" if self.credit else "-"
        return f"{self.date} {sign}{self.amount} {self.name}"


class BankAccess(models.Model):
    """Ein Zugang zum Online-Banking einer Bank; mehrere Konten können dazugehören.

    Die PIN steht hier nicht und nirgends sonst: Sie kommt bei jedem Vorgang vom Nutzer.
    ``state`` ist der Sitzungsstand der Bank (Kundensystem-ID, Parameter), verschlüsselt."""

    class Way(models.TextChoices):
        FINTS = "fints", gettext_lazy("FinTS")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    name = models.CharField("Bezeichnung", max_length=100)
    way = models.CharField("Bankweg", max_length=10, choices=Way.choices, default=Way.FINTS)
    bank_code = models.CharField("Bankleitzahl", max_length=8)
    url = models.CharField("FinTS-Adresse", max_length=200)
    login = EncryptedCharField("Anmeldename", max_length=100, strict=True)
    customer_id = EncryptedCharField("Kunden-ID", max_length=100, blank=True, strict=True)
    tan_mechanism = models.CharField("TAN-Verfahren", max_length=10, blank=True)
    tan_mechanism_name = models.CharField("Name des TAN-Verfahrens", max_length=100, blank=True)
    tan_medium = models.CharField("TAN-Medium", max_length=100, blank=True)
    state = EncryptedTextField("Sitzungsstand der Bank", blank=True, strict=True)
    # IBANs der Konten, die die Bank zu diesem Zugang meldet
    ibans = models.JSONField("Konten bei der Bank", default=list, blank=True)
    ready = models.BooleanField("eingerichtet", default=False)
    last_success = models.DateTimeField("letzter erfolgreicher Kontakt", null=True, blank=True)
    # Fehlversuche mit der PIN: Banken sperren nach wenigen; HUBIplan bremst vorher
    failures = models.PositiveSmallIntegerField("Fehlversuche", default=0)
    locked_until = models.DateTimeField("gesperrt bis", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Bankzugang"
        verbose_name_plural = "Bankzugänge"
        ordering = ["name", "pk"]

    def __str__(self) -> str:
        return self.name


class BankTask(models.Model):
    """Ein Vorgang bei der Bank (einrichten, Umsätze abrufen), auch zum Nachvollziehen.

    Wartet die Bank auf eine Freigabe, liegt der angehaltene Dialog verschlüsselt in
    ``dialog`` (ohne PIN) und wird nach Ende oder Ablauf geleert."""

    class Kind(models.TextChoices):
        SETUP = "setup", gettext_lazy("Einrichten")
        FETCH = "fetch", gettext_lazy("Umsätze abrufen")

    class Status(models.TextChoices):
        TAN = "tan", gettext_lazy("wartet auf Freigabe")
        DONE = "done", gettext_lazy("erledigt")
        FAILED = "failed", gettext_lazy("fehlgeschlagen")
        EXPIRED = "expired", gettext_lazy("abgelaufen")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    access = models.ForeignKey(BankAccess, on_delete=models.CASCADE, related_name="tasks")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    status = models.CharField(max_length=10, choices=Status.choices)
    dialog = EncryptedJSONField("angehaltener Dialog", default=dict, blank=True, strict=True)
    decoupled = models.BooleanField("Freigabe in der App", default=False)
    expires_at = models.DateTimeField(null=True, blank=True)
    message = models.CharField("Ergebnis", max_length=300, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Bankvorgang"
        verbose_name_plural = "Bankvorgänge"
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["organization", "access", "status"])]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.created_at:%d.%m.%Y %H:%M}"
