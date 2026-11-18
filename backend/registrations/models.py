"""Verbindliche Anmeldung mit Teilnahmegebühr (konzepte/veranstaltungen-anmeldung-gebuehr.md).

Ein Termin hat entweder Zu- und Absagen (``events.EventResponse``) oder eine verbindliche
Anmeldung (``RegistrationSetup``). Die Anmeldung hat Tarife (``PriceOption``), jeder Tarif
eine oder mehrere Preisstufen (``PriceStep``, z. B. Early Bird bis zu einem Datum oder für die
ersten Plätze). Eine ``Registration`` ist, was eine Person abschickt; sie nennt eine oder
mehrere ``Participant`` (sie selbst, Familie, Gäste) und bekommt eine Rechnung.

Preise werden bei der Anmeldung festgehalten (Betrag und Name der Stufe am Teilnehmer) und
ändern sich danach nicht mehr.
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.encfields import EncryptedCharField, EncryptedDateField, EncryptedTextField

MAX_PERSONS = 20
MAX_PRICES = 12
MAX_STEPS = 6


class RegistrationSetup(models.Model):
    """Anmeldeverfahren an einem Termin."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    event = models.OneToOneField(
        "events.Event", on_delete=models.CASCADE, related_name="registration_setup"
    )
    # Anmeldung möglich ab (leer: sofort) und bis (Anmeldeschluss)
    opens_at = models.DateTimeField(_("Anmeldung ab"), null=True, blank=True)
    closes_at = models.DateTimeField(_("Anmeldeschluss"))
    # Von Hand geschlossen (auch vor dem Anmeldeschluss)
    is_open = models.BooleanField(_("Anmeldung offen"), default=True)
    capacity = models.PositiveIntegerField(
        _("Plätze"), null=True, blank=True, validators=[MinValueValidator(1)]
    )
    max_persons = models.PositiveSmallIntegerField(
        _("Personen je Anmeldung"),
        default=6,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_PERSONS)],
    )
    # Mitglieder dürfen Gäste (Nichtmitglieder) mit Namen mit anmelden
    guests_allowed = models.BooleanField(_("Gäste erlaubt"), default=True)
    # Zahlungsziel in Tagen nach der Anmeldung (höchstens bis zum Tag vor Beginn)
    due_days = models.PositiveSmallIntegerField(
        _("Zahlungsziel (Tage)"), default=14, validators=[MaxValueValidator(90)]
    )
    category = models.ForeignKey(
        "finance.Category",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Kategorie in der Kasse"),
    )
    terms = models.TextField(_("Teilnahmebedingungen"), blank=True, max_length=5000)
    # Stufe A3: Warteliste, Ersatzperson, Stornoregel, Verfall unbezahlter Anmeldungen
    waitlist = models.BooleanField(_("Warteliste"), default=False, db_default=False)
    substitute_allowed = models.BooleanField(
        _("Ersatzperson erlaubt"), default=True, db_default=True
    )
    # Staffel: [{"days": 30, "percent": 50}, …] heißt „weniger als 30 Tage vorher: 50 %“
    cancel_rules = models.JSONField(_("Stornogebühren"), default=list, blank=True, null=True)
    cancel_fee_fixed = models.DecimalField(
        _("Bearbeitungsgebühr bei Abmeldung"),
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal(0))],
    )
    # Unbezahlte Anmeldungen verfallen so viele Tage vor Beginn (leer: nie)
    expire_unpaid_days = models.PositiveSmallIntegerField(
        _("Unbezahlte Anmeldungen verfallen"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(90)],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Anmeldung am Termin"
        verbose_name_plural = "Anmeldungen an Terminen"

    def __str__(self) -> str:
        return f"Anmeldung zu {self.event_id}"

    def save(self, *args, **kwargs):
        self.organization_id = self.event.organization_id
        super().save(*args, **kwargs)


class PriceOption(models.Model):
    """Tarif: Preis für eine Person, mit Bedingung."""

    class Applies(models.TextChoices):
        ALL = "all", _("alle")
        MEMBERS = "members", _("nur Mitglieder")
        GUESTS = "guests", _("nur Gäste")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    setup = models.ForeignKey(RegistrationSetup, on_delete=models.CASCADE, related_name="prices")
    name = models.CharField(_("Name"), max_length=100)
    name_en = models.CharField(_("Name (Englisch)"), max_length=100, blank=True)
    applies = models.CharField(max_length=10, choices=Applies.choices, default=Applies.ALL)
    # Alter am ersten Tag der Veranstaltung
    age_from = models.PositiveSmallIntegerField(null=True, blank=True)
    age_to = models.PositiveSmallIntegerField(null=True, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    # Umsatzsteuer im Betrag enthalten (leer/0 = keine)
    vat_rate = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    position = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.organization_id = self.setup.organization_id
        super().save(*args, **kwargs)


class PriceStep(models.Model):
    """Preisstufe eines Tarifs, z. B. Early Bird bis 31.03. oder für die ersten 30 Plätze.

    Stufen gelten nacheinander (``position``); eine Stufe endet am Datum ``until_date``
    (einschließlich) oder wenn ``until_count`` Personen sie gebucht haben, was zuerst kommt.
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    price = models.ForeignKey(PriceOption, on_delete=models.CASCADE, related_name="steps")
    name = models.CharField(_("Name"), max_length=60, blank=True)
    amount = models.DecimalField(
        _("Betrag"), max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal(0))]
    )
    until_date = models.DateField(_("gilt bis"), null=True, blank=True)
    until_count = models.PositiveIntegerField(
        _("für die ersten"), null=True, blank=True, validators=[MinValueValidator(1)]
    )
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self) -> str:
        return f"{self.name} {self.amount}"

    def save(self, *args, **kwargs):
        self.organization_id = self.price.organization_id
        super().save(*args, **kwargs)


class Registration(models.Model):
    """Eine Anmeldung: wer anmeldet, für wen, und die Rechnung dazu."""

    class Status(models.TextChoices):
        REGISTERED = "registered", _("angemeldet")
        WAITING = "waiting", _("Warteliste")
        CANCELLED = "cancelled", _("abgemeldet")

    class Source(models.TextChoices):
        MEMBER = "member", _("Mitgliederbereich")
        APP = "app", _("App")
        BOARD = "board", _("Verwaltung")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    setup = models.ForeignKey(
        RegistrationSetup, on_delete=models.PROTECT, related_name="registrations"
    )
    # Nummer je Einheit und Jahr der Anmeldung, z. B. A2027-0012
    year = models.PositiveSmallIntegerField()
    number = models.PositiveIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REGISTERED)
    # Anmeldende Person, wenn sie Mitglied ist (leer: Gast oder Daten gelöscht)
    membership = models.ForeignKey(
        "members.Membership",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="event_registrations",
    )
    name = EncryptedCharField(_("Name"), max_length=200, strict=True)
    email = EncryptedCharField(_("E-Mail"), max_length=254, blank=True, strict=True)
    phone = EncryptedCharField(_("Telefon"), max_length=50, blank=True, strict=True)
    address = EncryptedTextField(_("Anschrift"), blank=True, strict=True)
    note = EncryptedCharField(_("Bemerkung"), max_length=500, blank=True, strict=True)
    language = models.CharField(max_length=8, default="de")
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MEMBER)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    invoice = models.ForeignKey(
        "billing.Invoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    confirmation_sent_at = models.DateTimeField(null=True, blank=True)
    payment_confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=300, blank=True)
    # Von der Warteliste nachgerückt; bis free_cancel_until kostenfrei abmelden
    moved_up_at = models.DateTimeField(null=True, blank=True)
    free_cancel_until = models.DateTimeField(null=True, blank=True)
    # Stornogebühr (Summe) und die Rechnung dazu
    cancel_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"), db_default=Decimal("0.00")
    )
    fee_invoice = models.ForeignKey(
        "billing.Invoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    # Gäste ohne Mitgliedschaft: Daten nach dieser Zeit anonymisieren
    purged_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Anmeldung"
        verbose_name_plural = "Anmeldungen"
        ordering = ["created_at", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "year", "number"], name="anmeldenummer_eindeutig"
            )
        ]
        indexes = [models.Index(fields=["setup", "status"])]

    def __str__(self) -> str:
        return self.display_number

    def save(self, *args, **kwargs):
        self.organization_id = self.setup.organization_id
        super().save(*args, **kwargs)

    @property
    def display_number(self) -> str:
        return f"A{self.year}-{self.number:04d}"


class Participant(models.Model):
    """Eine Person einer Anmeldung, mit Tarif und festgehaltenem Preis."""

    class Status(models.TextChoices):
        ACTIVE = "active", _("dabei")
        CANCELLED = "cancelled", _("abgemeldet")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    registration = models.ForeignKey(
        Registration, on_delete=models.CASCADE, related_name="participants"
    )
    membership = models.ForeignKey(
        "members.Membership",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    name = EncryptedCharField(_("Name"), max_length=200, strict=True)
    birth_date = EncryptedDateField(_("Geburtsdatum"), null=True, blank=True)
    price = models.ForeignKey(PriceOption, on_delete=models.PROTECT, related_name="+")
    step = models.ForeignKey(
        PriceStep, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Bei der Anmeldung festgehalten
    price_name = models.CharField(max_length=170, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Teilnehmende"
        verbose_name_plural = "Teilnehmende"
        ordering = ["position", "pk"]
        indexes = [models.Index(fields=["price", "status"])]

    def __str__(self) -> str:
        return f"participant {self.pk}"

    def save(self, *args, **kwargs):
        self.organization_id = self.registration.organization_id
        super().save(*args, **kwargs)
