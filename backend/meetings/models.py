"""Versammlungen und Sitzungen (konzepte/versammlungen.md).

Eine Versammlung (``Meeting``) ist immer ein Termin im Kalender, dazu kommen Art,
Tagesordnung und später Einladung, Anwesenheit, Beschlüsse und Protokoll. Die Art
(``MeetingKind``) hält die Voreinstellungen des Vereins, z. B. die Einladungsfrist.
Versammlungen gehören zu einem Verein oder Dachverband oder zu einer Untereinheit
(Spalte ``department``, wie beim Material).
"""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.encfields import EncryptedCharField, EncryptedTextField


class MeetingKind(models.Model):
    class Base(models.TextChoices):
        GENERAL = "general", _("Mitgliederversammlung")
        BOARD = "board", _("Vorstandssitzung")
        COMMITTEE = "committee", _("Gremium oder Ausschuss")

    class Form(models.TextChoices):
        MAIL = "mail", _("E-Mail, sonst Brief")
        LETTER = "letter", _("Brief an alle")

    class MinutesFor(models.TextChoices):
        BOARD = "board", _("nur Rollen mit Leserecht")
        VOTERS = "voters", _("auch alle Stimmberechtigten")

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    department = models.ForeignKey(
        "organizations.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    name = models.CharField(_("Name"), max_length=100)
    base = models.CharField(max_length=10, choices=Base.choices, default=Base.GENERAL)
    invite_days = models.PositiveSmallIntegerField(
        _("Einladungsfrist in Tagen"),
        default=14,
        validators=[MaxValueValidator(365)],
    )
    invite_form = models.CharField(max_length=10, choices=Form.choices, default=Form.MAIL)
    # Stimmberechtigt: Mitglieder dieser Arten ab diesem Alter (leer: alle Arten)
    voter_types = models.JSONField(default=list, blank=True)
    voter_min_age = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(120)]
    )
    # Beschlussfähig ab Anteil (Prozent) oder Zahl der Stimmberechtigten; leer: immer
    quorum_percent = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    quorum_count = models.PositiveIntegerField(null=True, blank=True)
    proxies_allowed = models.BooleanField(_("Vertretung mit Vollmacht"), default=False)
    minutes_for = models.CharField(
        max_length=10, choices=MinutesFor.choices, default=MinutesFor.BOARD
    )
    position = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "name", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "department", "name"],
                name="meetingkind_unique_name",
                nulls_distinct=False,
            )
        ]

    def __str__(self):
        return self.name


class Meeting(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("in Vorbereitung")
        INVITED = "invited", _("eingeladen")
        HELD = "held", _("durchgeführt")
        MINUTES = "minutes", _("Protokoll in Arbeit")
        DONE = "done", _("Protokoll freigegeben")
        CANCELLED = "cancelled", _("abgesagt")

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    department = models.ForeignKey(
        "organizations.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    kind = models.ForeignKey(MeetingKind, on_delete=models.PROTECT, related_name="meetings")
    event = models.OneToOneField("events.Event", on_delete=models.PROTECT, related_name="meeting")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    chair = EncryptedCharField(_("Leitung"), max_length=200, blank=True)
    minute_taker = EncryptedCharField(_("Protokollführung"), max_length=200, blank=True)
    note = EncryptedTextField(_("Notiz"), blank=True)
    # Einladung als Rundschreiben (Schritt V2); eingeladen, sobald es versendet ist
    circular = models.ForeignKey(
        "circulars.Circular",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="meetings",
    )
    invited_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["organization", "department"])]

    def __str__(self):
        return f"meeting {self.pk}"


class AgendaItem(models.Model):
    class Type(models.TextChoices):
        REPORT = "report", _("Bericht")
        RESOLUTION = "resolution", _("Beschluss")
        ELECTION = "election", _("Wahl")
        OTHER = "other", _("Sonstiges")

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="agenda")
    position = models.PositiveSmallIntegerField()
    title = EncryptedCharField(_("Titel"), max_length=300)
    description = EncryptedTextField(_("Erläuterung"), blank=True)
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.OTHER)

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self):
        return f"agenda item {self.pk}"


class Attendance(models.Model):
    """Anwesenheit bei einer Versammlung (Schritt V3).

    Mitglieder stehen mit ihrer Mitgliedschaft hier, Gäste nur mit Namen. Der Name wird
    beim Eintragen festgehalten, damit die Liste auch nach einem Austritt lesbar bleibt.
    """

    class Status(models.TextChoices):
        PRESENT = "present", _("anwesend")
        EXCUSED = "excused", _("entschuldigt")
        REPRESENTED = "represented", _("vertreten")

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="attendance")
    membership = models.ForeignKey(
        "members.Membership", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    name = EncryptedCharField(_("Name"), max_length=200)
    status = models.CharField(max_length=12, choices=Status.choices)
    voter = models.BooleanField(default=False)
    represented_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="proxies"
    )
    recorded_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["meeting", "membership"],
                condition=models.Q(membership__isnull=False),
                name="attendance_once_per_member",
            )
        ]

    def __str__(self):
        return f"attendance {self.pk}"
