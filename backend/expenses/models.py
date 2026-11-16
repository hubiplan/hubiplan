"""Auslagen erstatten (docs/auslagen.md).

Ein Mitglied legt für den Verein Geld aus und fordert genau diesen Betrag zurück
(Aufwendungsersatz, § 670 BGB). Der Antrag (``ExpenseClaim``) hat Positionen, Belege und
einen Verlauf. Gebucht wird erst bei der Auszahlung: Dann entsteht eine Ausgabe im
Kassenbuch, und die Belege des Antrags werden Belege dieser Buchung.

Alle Zeilen liegen im Datenbereich des Vereins (``organization``) und stehen unter
Row-Level Security (Migration 0002).
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.encfields import EncryptedCharField, EncryptedJSONField, EncryptedTextField
from core.privatefiles import PrivateFileField
from exchange.models import private_storage

# Vorgaben (Fachfragen AE-5, AE-13, AE-17)
DEFAULT_SELF_LIMIT = Decimal("200.00")
DEFAULT_KM_RATE = Decimal("0.30")
DEFAULT_HINT_MONTHS = 3


class ExpenseSettings(models.Model):
    """Einstellungen je Verein."""

    class Submitters(models.TextChoices):
        MEMBERS = "members", _("alle aktiven Mitglieder mit Zugang")
        OFFICERS = "officers", _("nur Personen mit Amt oder Rolle")

    organization = models.OneToOneField(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    submitters = models.CharField(
        max_length=10, choices=Submitters.choices, default=Submitters.MEMBERS
    )
    # Eigene Auslage bis zu diesem Betrag selbst auszahlen, nachträglich sichten (AE-5)
    self_limit = models.DecimalField(max_digits=10, decimal_places=2, default=DEFAULT_SELF_LIMIT)
    # Ab diesem Betrag zwei Freigaben (leer: nie; AE-7)
    second_from = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # Hinweis, wenn der Kauf länger zurückliegt (AE-13)
    hint_months = models.PositiveSmallIntegerField(default=DEFAULT_HINT_MONTHS)
    # Untereinheiten, deren Leitung Auslagen vorher sachlich bestätigt (AE-6)
    confirm_departments = models.JSONField(default=list, blank=True)
    # Fahrtkosten (AE-17)
    mileage_enabled = models.BooleanField(default=True)
    km_rate = models.DecimalField(max_digits=5, decimal_places=2, default=DEFAULT_KM_RATE)
    # Aufwandsspende nur mit vorher bestehendem Anspruch (AE-18): Satzung oder Beschluss
    waiver_basis = models.CharField(max_length=300, blank=True)
    waiver_basis_date = models.DateField(null=True, blank=True)
    # Vorschüsse (A5)
    advances_enabled = models.BooleanField(default=False)
    # Einreichen über einen persönlichen Link für Personen ohne Zugang (A6)
    links_enabled = models.BooleanField(default=False)
    # Fortlaufende Nummer je Geschäftsjahr: {"2026": 12}
    counters = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Auslagen {self.organization_id}"


def file_path(instance, filename: str) -> str:
    stamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
    return f"expenses/{instance.organization_id}/{stamp}-{filename}"


class ExpenseClaim(models.Model):
    class Kind(models.TextChoices):
        EXPENSE = "expense", _("Auslage mit Beleg")
        MILEAGE = "mileage", _("Fahrtkosten")
        ADVANCE = "advance", _("Vorschuss")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Entwurf")
        SUBMITTED = "submitted", _("eingereicht")
        QUESTION = "question", _("Rückfrage")
        CONFIRMED = "confirmed", _("sachlich bestätigt")
        APPROVED = "approved", _("freigegeben")
        PAID = "paid", _("ausgezahlt")
        REJECTED = "rejected", _("abgelehnt")
        WITHDRAWN = "withdrawn", _("zurückgezogen")
        WAIVED = "waived", _("verzichtet (Spende)")

    class InvoiceTo(models.TextChoices):
        CLUB = "club", _("den Verein")
        ME = "me", _("mich")
        NONE = "none", _("ohne Namen (Kassenbon)")

    class Payout(models.TextChoices):
        BANK = "bank", _("Überweisung")
        CASH = "cash", _("bar")
        WAIVER = "waiver", _("Verzicht (Spende)")

    class Source(models.TextChoices):
        PORTAL = "portal", _("Mitgliederbereich")
        APP = "app", _("App")
        TREASURY = "treasury", _("von der Kasse erfasst")
        LINK = "link", _("persönlicher Link")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.EXPENSE)
    # Nummer A2026-0001, beim Einreichen vergeben
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    number = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.PORTAL)
    # Antragsteller: Mitglied (sonst Name/Mail bei Personen ohne Zugang)
    membership = models.ForeignKey(
        "members.Membership", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    name = EncryptedCharField(max_length=200, blank=True, strict=True)
    email = EncryptedCharField(max_length=254, blank=True, strict=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Über einen persönlichen Link eingereicht (A6)
    link = models.ForeignKey(
        "ExpenseLink", on_delete=models.SET_NULL, null=True, blank=True, related_name="claims"
    )
    purpose = EncryptedTextField(max_length=1000, blank=True, strict=True)
    # Wenn der Betrag von der Belegsumme abweicht: welcher Teil (z. B. „nur Posten 1–3“)
    note = EncryptedCharField(max_length=300, blank=True, strict=True)
    purchase_date = models.DateField(null=True, blank=True)
    department = models.ForeignKey(
        "organizations.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    project = models.ForeignKey(
        "finance.Project", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    invoice_to = models.CharField(max_length=5, choices=InvoiceTo.choices, default=InvoiceTo.NONE)
    payout = models.CharField(max_length=6, choices=Payout.choices, default=Payout.BANK)
    # Kontoinhaber, IBAN, BIC; nach der Auszahlung geleert (AE-10)
    payee = EncryptedJSONField(default=dict, blank=True, strict=True)
    # Fahrtkosten: Strecke, Kilometer, Satz zum Zeitpunkt des Antrags
    route = EncryptedCharField(max_length=300, blank=True, strict=True)
    km = models.DecimalField(max_digits=8, decimal_places=1, null=True, blank=True)
    km_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    # Abrechnung eines Vorschusses: dieser Vorschuss wird verrechnet
    advance = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="settlement"
    )
    # Freigegebener Betrag (kleiner als die Summe, wenn die Kasse kürzt)
    approved_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    reduce_reason = models.CharField(max_length=300, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    # Zweite Freigabe bei Beträgen ab ExpenseSettings.second_from
    second_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    second_at = models.DateTimeField(null=True, blank=True)
    # Eigene Auslage unter der Kleinbetragsgrenze: selbst freigegeben, später gesichtet
    self_approved = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reject_reason = models.CharField(max_length=500, blank=True)
    booking = models.ForeignKey(
        "finance.Booking", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    donation = models.OneToOneField(
        "finance.Donation", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    # Belege abgelehnter/zurückgezogener Anträge gelöscht (Aufbewahrung, AE-11)
    files_purged_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["organization", "status"])]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "number"],
                condition=~models.Q(number=""),
                name="auslage_nummer_einmal",
            ),
        ]

    def __str__(self) -> str:
        return self.number or f"Auslage {self.pk}"

    @property
    def total(self) -> Decimal:
        return sum((line.amount for line in self.lines.all()), Decimal("0.00"))

    @property
    def amount_due(self) -> Decimal:
        """Auszuzahlender Betrag: freigegeben oder Summe, abzüglich eines Vorschusses."""
        base = self.approved_amount if self.approved_amount is not None else self.total
        if self.advance_id and self.advance.status == self.Status.PAID:
            base -= self.advance.payout_amount
        return base

    @property
    def payout_amount(self) -> Decimal:
        return self.approved_amount if self.approved_amount is not None else self.total


class ExpenseLine(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    claim = models.ForeignKey(ExpenseClaim, on_delete=models.CASCADE, related_name="lines")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    text = EncryptedCharField(max_length=200, blank=True, strict=True)
    category = models.ForeignKey(
        "finance.Category", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="auslage_betrag_positiv")
        ]

    def __str__(self) -> str:
        return f"{self.amount}"


class ExpenseFile(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    claim = models.ForeignKey(ExpenseClaim, on_delete=models.CASCADE, related_name="files")
    file = PrivateFileField(storage=private_storage, upload_to=file_path, blank=True)
    name = models.CharField(max_length=200)
    content_type = models.CharField(max_length=100)
    size = models.PositiveIntegerField(default=0)
    sha256 = models.CharField(max_length=64)
    # Aus einer E-Rechnung gelesen (Summe, Datum, Verkäufer)
    einvoice = EncryptedJSONField(default=dict, blank=True, strict=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Nach der Auszahlung: dieser Beleg an der Buchung
    receipt = models.OneToOneField(
        "finance.Receipt", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["created_at", "pk"]
        indexes = [models.Index(fields=["organization", "sha256"])]

    def __str__(self) -> str:
        return self.name


class ExpenseEvent(models.Model):
    """Verlauf: jeder Schritt mit Person, Zeit und Bemerkung (auch Rückfragen)."""

    class Kind(models.TextChoices):
        CREATED = "created", _("angelegt")
        SUBMITTED = "submitted", _("eingereicht")
        QUESTION = "question", _("Rückfrage")
        ANSWER = "answer", _("Antwort")
        CONFIRMED = "confirmed", _("sachlich bestätigt")
        APPROVED = "approved", _("freigegeben")
        SECOND = "second", _("zweite Freigabe")
        SELF = "self", _("selbst freigegeben")
        REVIEWED = "reviewed", _("nachträglich gesichtet")
        REJECTED = "rejected", _("abgelehnt")
        WITHDRAWN = "withdrawn", _("zurückgezogen")
        PAID = "paid", _("ausgezahlt")
        REOPENED = "reopened", _("Auszahlung storniert")
        WAIVED = "waived", _("verzichtet")
        FILE = "file", _("Beleg ergänzt")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    claim = models.ForeignKey(ExpenseClaim, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Name zum Zeitpunkt (bleibt lesbar, wenn das Konto gelöscht wird)
    who = EncryptedCharField(max_length=200, blank=True, strict=True)
    text = EncryptedTextField(max_length=2000, blank=True, strict=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self) -> str:
        return self.kind


class ExpenseLink(models.Model):
    """Persönlicher Link zum Einreichen für Personen ohne Zugang (A6).

    Der Link enthält ein Geheimnis; gespeichert wird nur dessen Prüfsumme. Er gilt für
    eine Person, höchstens 90 Tage und ist widerrufbar."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    name = EncryptedCharField(max_length=200, strict=True)
    email = EncryptedCharField(max_length=254, blank=True, strict=True)
    membership = models.ForeignKey(
        "members.Membership", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    valid_until = models.DateField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Link {self.pk}"


class TransferRun(models.Model):
    """Sammelüberweisung (pain.001) für freigegebene Auslagen (A3).

    Wie bei den Musikern: Die Datei geht ins Onlinebanking. Anders als dort entstehen die
    Ausgabebuchungen hier beim ersten Herunterladen der Datei; vorher lässt sich der Lauf
    aufheben."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    reference = models.UUIDField(unique=True, editable=False)
    bank_account = models.ForeignKey("finance.Account", on_delete=models.PROTECT, related_name="+")
    execution_date = models.DateField()
    debtor = EncryptedJSONField(default=dict, strict=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    exported_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self) -> str:
        return f"Sammelüberweisung {self.reference}"


class TransferItem(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    run = models.ForeignKey(TransferRun, on_delete=models.CASCADE, related_name="items")
    claim = models.ForeignKey(ExpenseClaim, on_delete=models.PROTECT, related_name="transfers")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payee = EncryptedJSONField(default=dict, strict=True)
    released = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["claim"],
                condition=models.Q(released=False),
                name="auslage_ein_lauf",
            ),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="auslage_lauf_positiv"),
        ]

    def __str__(self) -> str:
        return f"{self.claim_id}: {self.amount}"
