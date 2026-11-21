"""Training und Anwesenheit, Schießbuch für den Nachweis nach § 14 WaffG (docs/training.md).

- ``TrainingSession``: ein Übungsabend oder Training des Vereins oder einer Untereinheit, auf
  Wunsch zu einem Termin. Die Leitung öffnet das Einchecken; ihre Seite zeigt dann einen
  QR-Code, der alle 30 Sekunden wechselt (wie bei Versammlungen).
- ``Attendance``: wer da war, von Hand eingetragen oder per QR-Code selbst.
- ``ShootingEntry``: ein Eintrag im Schießbuch eines Mitglieds (nur mit Modul „Schießsport“).
  Er entsteht aus der Anwesenheit bei einem Schießtraining, vom Vorstand von Hand oder als
  Meldung des Mitglieds, die der Vorstand bestätigt. Für den Nachweis zählen nur bestätigte
  Einträge mit erlaubnispflichtigen Waffen.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.encfields import EncryptedCharField

MAX_NOTE = 300


class WeaponClass(models.TextChoices):
    SHORT = "short", _("Kurzwaffe")
    LONG = "long", _("Langwaffe")


class TrainingSession(models.Model):
    class Kind(models.TextChoices):
        PRACTICE = "practice", _("Übungsabend")
        TRAINING = "training", _("Training")
        COMPETITION = "competition", _("Wettkampf")
        OTHER = "other", _("Sonstiges")

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    department = models.ForeignKey(
        "organizations.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    event = models.ForeignKey(
        "events.Event", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    date = models.DateField(_("Datum"))
    starts_at = models.TimeField(_("Beginn"), null=True, blank=True)
    ends_at = models.TimeField(_("Ende"), null=True, blank=True)
    title = models.CharField(_("Bezeichnung"), max_length=200)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.PRACTICE)
    location = models.CharField(_("Ort"), max_length=200, blank=True)
    # Übungsleiter/in als Name (auch Gäste oder Trainer anderer Vereine)
    leader = models.CharField(_("Leitung"), max_length=200, blank=True)
    note = EncryptedCharField(_("Notiz"), max_length=MAX_NOTE, blank=True)
    # Schießtermin: Anwesende bekommen einen Eintrag im Schießbuch (Modul „Schießsport“)
    shooting = models.BooleanField(_("Schießtermin"), default=False)
    discipline = models.CharField(_("Disziplin"), max_length=100, blank=True)
    weapon_class = models.CharField(max_length=5, choices=WeaponClass.choices, blank=True)
    caliber = models.CharField(_("Kaliber"), max_length=40, blank=True)
    permit_required = models.BooleanField(_("erlaubnispflichtige Waffe"), default=True)
    checkin_open = models.BooleanField(default=False)
    checkin_key = models.CharField(max_length=64, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-starts_at", "-pk"]
        indexes = [models.Index(fields=["organization", "department", "date"])]

    def __str__(self):
        return f"training {self.pk}"


class Attendance(models.Model):
    class Source(models.TextChoices):
        HAND = "hand", _("von Hand")
        CODE = "code", _("per QR-Code")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    session = models.ForeignKey(
        TrainingSession, on_delete=models.CASCADE, related_name="attendances"
    )
    membership = models.ForeignKey("members.Membership", on_delete=models.CASCADE, related_name="+")
    source = models.CharField(max_length=5, choices=Source.choices, default=Source.HAND)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["session", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "membership"], name="training_attendance_once"
            )
        ]
        indexes = [models.Index(fields=["organization", "membership"])]

    def __str__(self):
        return f"attendance {self.pk}"


class ShootingEntry(models.Model):
    class Status(models.TextChoices):
        REPORTED = "reported", _("gemeldet")
        CONFIRMED = "confirmed", _("bestätigt")
        REJECTED = "rejected", _("abgelehnt")

    class Source(models.TextChoices):
        TRAINING = "training", _("aus dem Training")
        BOARD = "board", _("vom Vorstand eingetragen")
        MEMBER = "member", _("vom Mitglied gemeldet")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    membership = models.ForeignKey("members.Membership", on_delete=models.CASCADE, related_name="+")
    # Aus der Anwesenheit bei einem Schießtermin; fällt mit ihr weg
    attendance = models.OneToOneField(
        Attendance, null=True, blank=True, on_delete=models.CASCADE, related_name="shooting"
    )
    date = models.DateField(_("Datum"))
    discipline = models.CharField(_("Disziplin"), max_length=100)
    weapon_class = models.CharField(max_length=5, choices=WeaponClass.choices)
    caliber = models.CharField(_("Kaliber"), max_length=40, blank=True)
    permit_required = models.BooleanField(_("erlaubnispflichtige Waffe"), default=True)
    own_weapon = models.BooleanField(_("eigene Waffe"), null=True, blank=True)
    competition = models.BooleanField(_("Wettkampf"), default=False)
    # Schießstand; leer heißt: Stand des eigenen Vereins
    place = models.CharField(_("Schießstand"), max_length=200, blank=True)
    external = models.BooleanField(_("in einem anderen Verein"), default=False)
    note = EncryptedCharField(_("Bemerkung"), max_length=MAX_NOTE, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CONFIRMED)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.BOARD)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Name zum Zeitpunkt der Bestätigung (bleibt, auch wenn das Konto später fehlt)
    confirmed_by_name = models.CharField(max_length=200, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-pk"]
        indexes = [
            models.Index(fields=["organization", "membership", "date"]),
            models.Index(fields=["organization", "status"]),
        ]

    def __str__(self):
        return f"shooting {self.pk}"
