"""Abrechnung: Einstellungen, Beitragssätze und Beitragsläufe."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext, gettext_lazy

ZERO = Decimal("0.00")


class Rhythm(models.TextChoices):
    YEARLY = "yearly", gettext_lazy("jährlich")
    HALFYEARLY = "halfyearly", gettext_lazy("halbjährlich")
    QUARTERLY = "quarterly", gettext_lazy("vierteljährlich")
    MONTHLY = "monthly", gettext_lazy("monatlich")


class ProRata(models.TextChoices):
    """Anteiliger Beitrag bei Eintritt oder Austritt im laufenden Zeitraum: je angefangenem
    Monat, Quartal oder Halbjahr, gezählt vom Beginn des Geschäftsjahres."""

    OFF = "off", gettext_lazy("nicht anteilig (voller Beitrag)")
    MONTH = "month", gettext_lazy("je angefangenem Monat")
    QUARTER = "quarter", gettext_lazy("je angefangenem Quartal")
    HALFYEAR = "halfyear", gettext_lazy("je angefangenem Halbjahr")


PRO_RATA_MONTHS = {ProRata.MONTH: 1, ProRata.QUARTER: 3, ProRata.HALFYEAR: 6}


PERIODS_PER_YEAR = {
    Rhythm.YEARLY: 1,
    Rhythm.HALFYEARLY: 2,
    Rhythm.QUARTERLY: 4,
    Rhythm.MONTHLY: 12,
}


class BillingSettings(models.Model):
    organization = models.OneToOneField(
        "organizations.Organization", on_delete=models.CASCADE, related_name="billing_settings"
    )
    rhythm = models.CharField(
        "Abrechnungsrhythmus", max_length=12, choices=Rhythm.choices, default=Rhythm.YEARLY
    )
    due_days = models.PositiveSmallIntegerField("Zahlungsziel in Tagen", default=14)
    # Alt (bis v2026.11): an/aus für „je angefangenem Monat“. Bleibt eine Fassung lang als
    # Spiegel von pro_rata_step erhalten, damit die vorige Fassung weiterläuft.
    pro_rata = models.BooleanField(
        "Eintritt im laufenden Zeitraum anteilig berechnen (je angefangenem Monat)",
        default=False,
    )
    pro_rata_step = models.CharField(
        "Beitrag bei Eintritt im laufenden Zeitraum",
        max_length=10,
        choices=ProRata.choices,
        default=ProRata.OFF,
        db_default=ProRata.OFF,
    )
    account = models.ForeignKey(
        "finance.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Konto für Überweisungen",
    )
    category = models.ForeignKey(
        "finance.Category",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Kategorie für Beitragszahlungen",
    )
    intro_text = models.TextField(
        "Text vor den Posten",
        blank=True,
        default="wir berechnen Ihnen den Mitgliedsbeitrag wie folgt:",
    )
    footer_text = models.TextField("Text unter der Rechnung", blank=True)
    qr_code = models.BooleanField("QR-Code für die Banking-App aufdrucken", default=True)
    # Umsatzsteuer (Standard: nicht ausgewiesen)
    vat_enabled = models.BooleanField("Umsatzsteuer auf Rechnungen ausweisen", default=False)
    vat_rate = models.DecimalField(
        "Steuersatz in Prozent", max_digits=4, decimal_places=2, default=Decimal("19.00")
    )
    tax_number = models.CharField("Steuernummer oder USt-IdNr.", max_length=50, blank=True)
    # Dachverband: Beitrag der Vereine je gemeldetem Mitglied (Jahresbeträge)
    club_rate_active = models.DecimalField(
        "je gemeldetem aktiven Mitglied", max_digits=10, decimal_places=2, null=True, blank=True
    )
    club_rate_passive = models.DecimalField(
        "je gemeldetem passiven Mitglied", max_digits=10, decimal_places=2, null=True, blank=True
    )
    club_base_amount = models.DecimalField(
        "Grundbetrag je Verein", max_digits=10, decimal_places=2, null=True, blank=True
    )
    # SEPA-Lastschrift; ausgeschaltet verschwinden Lastschriften und Mandate aus der Oberfläche
    sepa_enabled = models.BooleanField("SEPA-Lastschrift nutzen", default=False)
    creditor_id = models.CharField("Gläubiger-Identifikationsnummer", max_length=35, blank=True)
    prenotification_days = models.PositiveSmallIntegerField(
        "Vorabankündigung (Tage vor dem Einzug)", default=14
    )
    # E-Rechnung (XRechnung) für Beitragsrechnungen an Mitglieder mit Leitweg-ID (J8a)
    einvoice_members = models.BooleanField(
        "Rechnungen an Mitglieder mit Leitweg-ID als E-Rechnung (XRechnung)",
        default=False,
        db_default=False,
    )
    einvoice_contact = models.CharField(
        "Ansprechpartner für Rechnungsfragen", max_length=100, blank=True, default="", db_default=""
    )
    einvoice_phone = models.CharField(
        "Telefon für Rechnungsfragen", max_length=50, blank=True, default="", db_default=""
    )
    einvoice_email = models.EmailField(
        "E-Mail für Rechnungsfragen", blank=True, default="", db_default=""
    )
    einvoice_identifier = models.CharField(
        "Kennung des Rechnungsstellers",
        max_length=100,
        blank=True,
        default="",
        db_default="",
        help_text="z. B. Vereinsregisternummer; leer: aus dem Impressum",
    )

    # Arbeitsstunden (docs/arbeitsstunden.md): Pflicht nur in diesem Alter (zu Beginn des
    # Geschäftsjahres); leer = ohne Grenze
    work_min_age = models.PositiveSmallIntegerField(
        "Arbeitsstunden ab Alter", null=True, blank=True
    )
    work_max_age = models.PositiveSmallIntegerField(
        "Arbeitsstunden bis Alter", null=True, blank=True
    )

    class Meta:
        verbose_name = "Beitragseinstellungen"
        verbose_name_plural = "Beitragseinstellungen"

    def __str__(self) -> str:
        return f"Beitragseinstellungen {self.organization}"

    def save(self, *args, **kwargs):
        # Spiegel für die vorige Fassung (liest nur pro_rata)
        self.pro_rata = self.pro_rata_step != ProRata.OFF
        fields = kwargs.get("update_fields")
        if fields is not None and "pro_rata_step" in fields and "pro_rata" not in fields:
            kwargs["update_fields"] = [*fields, "pro_rata"]
        super().save(*args, **kwargs)

    @property
    def periods(self) -> int:
        return PERIODS_PER_YEAR[self.rhythm]

    @property
    def pro_rata_months(self) -> int:
        """Länge eines Anteils in Monaten, 0 = nicht anteilig."""
        return PRO_RATA_MONTHS.get(self.pro_rata_step, 0)


class FeeRate(models.Model):
    """Jahresbeitrag je Mitgliedsart."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    member_type = models.OneToOneField(
        "members.MemberType", on_delete=models.CASCADE, related_name="fee_rate"
    )
    amount = models.DecimalField("Jahresbeitrag", max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "Beitragssatz"
        verbose_name_plural = "Beitragssätze"

    def __str__(self) -> str:
        return f"{self.member_type}: {self.amount}"

    def clean(self):
        if self.amount is not None and self.amount < 0:
            raise ValidationError({"amount": gettext("Der Beitrag darf nicht negativ sein.")})


class WorkHourRule(models.Model):
    """Pflichtstunden je Mitgliedsart und Geschäftsjahr mit Ersatzbeitrag je fehlender Stunde.

    Geleistete Stunden zählen aus erledigten Helferschichten; fehlende Stunden kommen als
    Posten in den ersten Beitragslauf des folgenden Geschäftsjahres (docs/arbeitsstunden.md).
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    member_type = models.OneToOneField(
        "members.MemberType", on_delete=models.CASCADE, related_name="work_hour_rule"
    )
    hours = models.DecimalField("Pflichtstunden im Jahr", max_digits=5, decimal_places=2)
    rate = models.DecimalField("Ersatzbeitrag je fehlender Stunde", max_digits=8, decimal_places=2)

    class Meta:
        verbose_name = "Arbeitsstunden-Regel"
        verbose_name_plural = "Arbeitsstunden-Regeln"

    def __str__(self) -> str:
        return f"{self.member_type}: {self.hours} h × {self.rate}"


class AgeRate(models.Model):
    """Altersstufe: eigener Jahresbeitrag oder Abschlag in Prozent.

    Maßgeblich ist das Alter zu Beginn des Beitragsjahres. Ohne Mitgliedsart gilt
    die Stufe für alle Mitgliedsarten; eine Stufe mit Mitgliedsart geht vor.
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    name = models.CharField("Bezeichnung", max_length=100)
    member_type = models.ForeignKey(
        "members.MemberType",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="nur für Mitgliedsart",
    )
    min_age = models.PositiveSmallIntegerField("ab Alter", null=True, blank=True)
    max_age = models.PositiveSmallIntegerField("bis Alter (einschließlich)", null=True, blank=True)
    amount = models.DecimalField(
        "eigener Jahresbeitrag", max_digits=10, decimal_places=2, null=True, blank=True
    )
    discount_percent = models.DecimalField(
        "Abschlag in Prozent", max_digits=5, decimal_places=2, null=True, blank=True
    )

    class Meta:
        verbose_name = "Altersstufe"
        verbose_name_plural = "Altersstufen"
        ordering = ["min_age", "max_age", "name"]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        errors = {}
        if self.min_age is None and self.max_age is None:
            errors["max_age"] = gettext("Bitte ein Mindest- oder Höchstalter angeben.")
        if self.min_age is not None and self.max_age is not None and self.min_age > self.max_age:
            errors["max_age"] = gettext("Das Höchstalter liegt unter dem Mindestalter.")
        if (self.amount is None) == (self.discount_percent is None):
            errors["amount"] = gettext(
                "Bitte entweder einen eigenen Beitrag oder einen Abschlag angeben."
            )
        if self.amount is not None and self.amount < 0:
            errors["amount"] = gettext("Der Beitrag darf nicht negativ sein.")
        if self.discount_percent is not None and not (0 < self.discount_percent <= 100):
            errors["discount_percent"] = gettext("Der Abschlag liegt zwischen 0 und 100 Prozent.")
        if errors:
            raise ValidationError(errors)

    def matches(self, age: int) -> bool:
        if self.min_age is not None and age < self.min_age:
            return False
        return not (self.max_age is not None and age > self.max_age)


class SizeRate(models.Model):
    """Staffel nach Größe für Organisationsmitglieder (Mitarbeiter, Einwohner …, J8c).

    Eigener Jahresbeitrag ab einer Größe. Ohne Mitgliedsart gilt die Stufe für alle
    Mitgliedsarten; eine Stufe mit Mitgliedsart geht vor. Organisationen ohne Größe
    zahlen den Beitrag der Mitgliedsart.
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    name = models.CharField("Bezeichnung", max_length=100)
    member_type = models.ForeignKey(
        "members.MemberType",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="nur für Mitgliedsart",
    )
    min_size = models.PositiveIntegerField("ab Größe", null=True, blank=True)
    max_size = models.PositiveIntegerField("bis Größe (einschließlich)", null=True, blank=True)
    amount = models.DecimalField("Jahresbeitrag", max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "Größenstufe"
        verbose_name_plural = "Größenstufen"
        ordering = ["min_size", "max_size", "name"]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        errors = {}
        if self.min_size is None and self.max_size is None:
            errors["max_size"] = gettext("Bitte eine Mindest- oder Höchstgröße angeben.")
        if (
            self.min_size is not None
            and self.max_size is not None
            and self.min_size > self.max_size
        ):
            errors["max_size"] = gettext("Die Höchstgröße liegt unter der Mindestgröße.")
        if self.amount is not None and self.amount < 0:
            errors["amount"] = gettext("Der Beitrag darf nicht negativ sein.")
        if errors:
            raise ValidationError(errors)

    def matches(self, size: int) -> bool:
        if self.min_size is not None and size < self.min_size:
            return False
        return not (self.max_size is not None and size > self.max_size)


class FeeRun(models.Model):
    """Beitragslauf für einen Abrechnungszeitraum eines Geschäftsjahres."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    year = models.PositiveSmallIntegerField("Geschäftsjahr")
    rhythm = models.CharField("Rhythmus", max_length=12, choices=Rhythm.choices)
    period = models.PositiveSmallIntegerField("Zeitraum", default=1)
    start_date = models.DateField("von")
    end_date = models.DateField("bis")
    label = models.CharField("Bezeichnung", max_length=100)
    invoice_date = models.DateField("Rechnungsdatum")
    due_date = models.DateField("fällig am")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Kasse bestätigt, dass die Rechnungen ohne E-Mail per Post raus sind (UI-Audit NAF-06)
    post_done_at = models.DateField("Postversand erledigt am", null=True, blank=True)

    class Meta:
        verbose_name = "Beitragslauf"
        verbose_name_plural = "Beitragsläufe"
        ordering = ["-start_date", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "start_date", "end_date"], name="beitragslauf_einmal"
            )
        ]

    def __str__(self) -> str:
        return self.label
