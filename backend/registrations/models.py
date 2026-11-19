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

from core.encfields import (
    EncryptedCharField,
    EncryptedDateField,
    EncryptedJSONField,
    EncryptedTextField,
)

MAX_PERSONS = 20
MAX_PRICES = 12
MAX_STEPS = 6
MAX_ADDONS = 8
MAX_CHOICES = 10
MAX_QUESTIONS = 10
MAX_GUARDIANS = 2


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
    # Stufe A5: mit Verpflegung (nur dann Gesundheitsangaben, F11) und Minderjährige (F13)
    catering = models.BooleanField(_("mit Verpflegung"), default=False, db_default=False)
    minors = models.BooleanField(_("Minderjährige möglich"), default=False, db_default=False)
    # Stufe A4: öffentliches Formular /anmeldung/<public_key> (nur bei öffentlichen Terminen)
    public = models.BooleanField(_("Öffentliche Anmeldung"), default=False, db_default=False)
    public_key = models.CharField(max_length=40, unique=True, null=True, blank=True)
    # Stufe A8: Vereine des Dachverbands melden ihre Mitglieder gesammelt an (Rechnung an
    # den Verein)
    club_registration = models.BooleanField(
        _("Sammelanmeldung durch die Vereine"), default=False, db_default=False
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


class Per(models.TextChoices):
    PERSON = "person", _("je Person")
    REGISTRATION = "registration", _("je Anmeldung")


class AddOn(models.Model):
    """Zusatzleistung mit Auswahl, z. B. Busfahrt (+12 €) oder Menü (Schnitzel, Lachs, …)."""

    class Kind(models.TextChoices):
        MEAL = "meal", _("Essen")
        OTHER = "other", _("sonstiges")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    setup = models.ForeignKey(RegistrationSetup, on_delete=models.CASCADE, related_name="addons")
    name = models.CharField(_("Name"), max_length=100)
    name_en = models.CharField(_("Name (Englisch)"), max_length=100, blank=True)
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.OTHER)
    per = models.CharField(max_length=12, choices=Per.choices, default=Per.PERSON)
    # Pflicht: eine Auswahl muss getroffen werden (z. B. Menü)
    required = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.organization_id = self.setup.organization_id
        super().save(*args, **kwargs)


class AddOnChoice(models.Model):
    """Eine Auswahl einer Zusatzleistung mit Aufpreis (auch 0 €) und Platzgrenze."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    addon = models.ForeignKey(AddOn, on_delete=models.CASCADE, related_name="choices")
    name = models.CharField(_("Name"), max_length=100)
    name_en = models.CharField(_("Name (Englisch)"), max_length=100, blank=True)
    amount = models.DecimalField(
        _("Aufpreis"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal(0))],
    )
    vat_rate = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    position = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.organization_id = self.addon.organization_id
        super().save(*args, **kwargs)


class Question(models.Model):
    """Zusatzfrage ohne Preis. Gesundheitsangaben (``health``) nur mit Verpflegung (F11),
    freiwillig, mit Einwilligung, und nur für die Verwaltung sichtbar."""

    class Kind(models.TextChoices):
        TEXT = "text", _("Text")
        YESNO = "yesno", _("Ja/Nein")
        CHOICE = "choice", _("Auswahl")
        HEALTH = "health", _("Allergien und Unverträglichkeiten")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    setup = models.ForeignKey(RegistrationSetup, on_delete=models.CASCADE, related_name="questions")
    text = models.CharField(_("Frage"), max_length=200)
    text_en = models.CharField(_("Frage (Englisch)"), max_length=200, blank=True)
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.TEXT)
    choices = models.JSONField(default=list, blank=True)
    required = models.BooleanField(default=False)
    per = models.CharField(max_length=12, choices=Per.choices, default=Per.REGISTRATION)
    position = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self) -> str:
        return self.text

    def save(self, *args, **kwargs):
        self.organization_id = self.setup.organization_id
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
        PUBLIC = "public", _("öffentliches Formular")
        CLUB = "club", _("Sammelanmeldung des Vereins")

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
    # Stufe A8: Sammelanmeldung eines Vereins zu einem Termin seines Dachverbands
    club = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Verein"),
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
    # Antworten auf Zusatzfragen je Anmeldung: {"<Frage-ID>": Wert}
    answers = EncryptedJSONField(default=dict, blank=True, db_default={})
    # Einwilligung in die Verarbeitung der Gesundheitsangaben (Art. 9 DSGVO)
    health_consent_at = models.DateTimeField(null=True, blank=True)
    health_purged_at = models.DateTimeField(null=True, blank=True)
    # Öffentliches Formular (A4): Zufallswert im signierten Link „Anmeldung ansehen“;
    # leer heißt: kein Link (Mitglieder, Verwaltung) oder nach der Löschfrist erloschen
    access_nonce = models.CharField(max_length=24, blank=True, default="", db_default="")
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
    # Antworten auf Zusatzfragen je Person; Gesundheitsangaben getrennt (früher gelöscht)
    answers = EncryptedJSONField(default=dict, blank=True, db_default={})
    health = EncryptedTextField(_("Allergien und Unverträglichkeiten"), blank=True, db_default="")
    # Unter 18: Erziehungsberechtigte [{"name", "phone", "email", "address"}, …] (F13)
    guardians = EncryptedJSONField(default=list, blank=True, db_default=[])
    # Sammelanmeldung (A8): Mitgliedschaft im meldenden Verein (eigener Datenbereich, daher
    # nur die Kennung)
    club_member_id = models.PositiveBigIntegerField(null=True, blank=True)
    # Einlass vor Ort (A6): wann und von wem abgehakt
    checked_in_at = models.DateTimeField(_("eingelassen am"), null=True, blank=True)
    checked_in_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Eingelassen über einen Scan-Link (Bezeichnung zur Zeit des Scans)
    checked_in_via = models.CharField(max_length=100, blank=True, db_default="", default="")

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


class Booking(models.Model):
    """Gebuchte Zusatzleistung, je Person oder je Anmeldung, mit festgehaltenem Preis."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    registration = models.ForeignKey(
        Registration, on_delete=models.CASCADE, related_name="bookings"
    )
    # leer: je Anmeldung
    participant = models.ForeignKey(
        Participant, on_delete=models.CASCADE, null=True, blank=True, related_name="bookings"
    )
    choice = models.ForeignKey(AddOnChoice, on_delete=models.PROTECT, related_name="bookings")
    # Bei der Anmeldung festgehalten
    name = models.CharField(max_length=210)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    vat_rate = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["pk"]
        indexes = [models.Index(fields=["choice"])]

    def __str__(self) -> str:
        return f"booking {self.pk}"

    def save(self, *args, **kwargs):
        self.organization_id = self.registration.organization_id
        super().save(*args, **kwargs)


class PendingRegistration(models.Model):
    """Anmeldung über das öffentliche Formular, bis die E-Mail-Adresse bestätigt ist (A4).

    Erst mit dem Bestätigungslink wird daraus eine ``Registration`` mit Platz und Rechnung;
    unbestätigte Einträge werden nach ``expires_at`` gelöscht.
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    setup = models.ForeignKey(RegistrationSetup, on_delete=models.CASCADE, related_name="pending")
    token_hash = models.CharField(max_length=64, unique=True)
    email = EncryptedCharField(max_length=254, strict=True)
    # Alle Angaben des Formulars wie abgeschickt (geprüft beim Absenden und beim Bestätigen)
    data = EncryptedJSONField(default=dict)
    language = models.CharField(max_length=8, default="de")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        verbose_name = "unbestätigte Anmeldung"
        verbose_name_plural = "unbestätigte Anmeldungen"
        indexes = [models.Index(fields=["expires_at"])]

    def __str__(self) -> str:
        return f"pending {self.pk}"

    def save(self, *args, **kwargs):
        self.organization_id = self.setup.organization_id
        super().save(*args, **kwargs)


class Material(models.Model):
    """Material zum Ausgeben vor Ort, z. B. Namensschild, Tasche oder Leihgerät, wahlweise mit
    Rückgabe (A6)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    setup = models.ForeignKey(RegistrationSetup, on_delete=models.CASCADE, related_name="materials")
    name = models.CharField(_("Name"), max_length=100)
    returnable = models.BooleanField(_("mit Rückgabe"), default=False)
    position = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.organization_id = self.setup.organization_id
        super().save(*args, **kwargs)


class Handout(models.Model):
    """Ausgegebenes (und ggf. zurückgegebenes) Material je Person."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="handouts")
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="handouts")
    handed_out_at = models.DateTimeField()
    returned_at = models.DateTimeField(null=True, blank=True)
    # Scan-Link (Bezeichnung) oder leer, wenn in der Verwaltung abgehakt
    via = models.CharField(max_length=100, blank=True, default="")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["material", "participant"], name="registrations_handout_einmal"
            )
        ]

    def __str__(self) -> str:
        return f"handout {self.pk}"

    def save(self, *args, **kwargs):
        self.organization_id = self.material.organization_id
        super().save(*args, **kwargs)


class ScanLink(models.Model):
    """Link für Scanpersonal ohne Konto (A6): öffnet auf dem Handy nur den Kartenscanner,
    für den Einlass oder für eine Zusatzleistung (z. B. Essen). Gesucht wird über die
    Prüfsumme des Schlüssels; der Schlüssel selbst liegt verschlüsselt, damit der Link sich
    noch einmal anzeigen lässt."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    setup = models.ForeignKey(
        RegistrationSetup, on_delete=models.CASCADE, related_name="scan_links"
    )
    label = models.CharField(_("Bezeichnung"), max_length=100)
    # leer: Einlass; sonst wird diese Zusatzleistung eingelöst
    addon = models.ForeignKey(
        AddOn, on_delete=models.CASCADE, null=True, blank=True, related_name="scan_links"
    )
    # oder Material ausgeben bzw. zurücknehmen
    material = models.ForeignKey(
        Material, on_delete=models.CASCADE, null=True, blank=True, related_name="scan_links"
    )
    material_return = models.BooleanField(default=False)
    token = EncryptedCharField(max_length=100, strict=True)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField(_("gültig bis"))
    # Ohne Karte: Personal darf Angemeldete per Namenssuche einbuchen (nach Ausweisabgleich)
    allow_search = models.BooleanField(_("Namenssuche erlauben"), default=False)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    scans = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["pk"]

    def __str__(self) -> str:
        return self.label

    def save(self, *args, **kwargs):
        self.organization_id = self.setup.organization_id
        super().save(*args, **kwargs)


class Redemption(models.Model):
    """Eingelöste Zusatzleistung (z. B. Essen ausgegeben): einmal je gebuchter Leistung."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name="redemption")
    # wer die Karte vorgezeigt hat (bei Leistungen je Anmeldung eine der Personen)
    participant = models.ForeignKey(
        Participant, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    at = models.DateTimeField()
    link = models.ForeignKey(
        ScanLink, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["pk"]

    def __str__(self) -> str:
        return f"redemption {self.pk}"

    def save(self, *args, **kwargs):
        self.organization_id = self.booking.organization_id
        super().save(*args, **kwargs)
