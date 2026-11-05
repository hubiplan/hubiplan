"""Musikprofile und Besetzung ergänzen Mitglieder und Kalendereinträge."""

import uuid

from django.conf import settings
from django.core.validators import EmailValidator, MaxValueValidator
from django.db import models
from django.utils import timezone

from core.encfields import EncryptedCharField, EncryptedJSONField


class Musician(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    membership = models.OneToOneField(
        "members.Membership", on_delete=models.PROTECT, null=True, blank=True
    )
    name = EncryptedCharField(max_length=200, strict=True, blank=True)
    contact = EncryptedCharField(max_length=300, strict=True, blank=True)
    guest_email = EncryptedCharField(
        max_length=254,
        strict=True,
        blank=True,
        default="",
        db_default="",
        validators=[EmailValidator()],
    )
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name or f"Musiker {self.pk}"


class MusicianAbsence(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    musician = models.ForeignKey(Musician, on_delete=models.PROTECT, related_name="absences")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()

    class Meta:
        ordering = ["starts_at", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="musik_abwesenheit_zeitraum",
            )
        ]

    def __str__(self):
        return f"Musikerabwesenheit {self.pk}"


class Skill(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    musician = models.ForeignKey(Musician, on_delete=models.CASCADE, related_name="skills")
    instrument = models.CharField(max_length=100)
    register = models.CharField(max_length=100, blank=True)
    primary = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["musician", "instrument", "register"], name="musik_faehigkeit_einmal"
            )
        ]

    def __str__(self):
        return self.instrument


class EnsembleTemplate(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    name = models.CharField(max_length=150)
    note = models.CharField(max_length=1000, blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class EnsembleTemplatePosition(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    template = models.ForeignKey(
        EnsembleTemplate, on_delete=models.CASCADE, related_name="positions"
    )
    instrument = models.CharField(max_length=100)
    register = models.CharField(max_length=100, blank=True)
    required = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "instrument", "register"], name="besetzung_vorlage_stimme"
            ),
            models.CheckConstraint(
                condition=models.Q(required__gte=1, required__lte=500),
                name="besetzung_vorlage_anzahl",
            ),
        ]

    def __str__(self):
        return self.instrument


class Performance(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    event = models.OneToOneField(
        "events.Event", on_delete=models.PROTECT, related_name="performance"
    )
    customer = models.ForeignKey(
        "billing.BusinessPartner", on_delete=models.PROTECT, null=True, blank=True
    )
    meeting_at = models.DateTimeField(null=True, blank=True)
    meeting_place = models.CharField(max_length=300, blank=True)
    setup_at = models.DateTimeField(null=True, blank=True)
    uniform = models.CharField(max_length=300, blank=True)
    formation = models.CharField(
        max_length=12,
        choices=[("seated", "seated"), ("standing", "standing"), ("march", "march")],
        default="standing",
    )
    notes = EncryptedCharField(max_length=5000, blank=True, strict=True)
    remind_days = models.PositiveSmallIntegerField(
        default=3, db_default=3, validators=[MaxValueValidator(30)]
    )

    def __str__(self):
        return f"Auftritt {self.pk}"


class Position(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    performance = models.ForeignKey(Performance, on_delete=models.CASCADE, related_name="positions")
    instrument = models.CharField(max_length=100)
    register = models.CharField(max_length=100, blank=True)
    required = models.PositiveSmallIntegerField(default=1)

    def __str__(self):
        return self.instrument


class Assignment(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    performance = models.ForeignKey(
        Performance, on_delete=models.CASCADE, related_name="assignments"
    )
    position = models.ForeignKey(Position, on_delete=models.PROTECT)
    musician = models.ForeignKey(Musician, on_delete=models.PROTECT)
    status = models.CharField(
        max_length=12,
        choices=[("pending", "pending"), ("accepted", "accepted"), ("declined", "declined")],
        default="pending",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["performance", "musician"], name="musik_einteilung_einmal"
            )
        ]

    def __str__(self):
        return f"Einteilung {self.pk}"


class PerformanceNotice(models.Model):
    """Only fingerprints are retained; event details stay in the calendar."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    assignment = models.OneToOneField(Assignment, on_delete=models.CASCADE, related_name="notice")
    fingerprint = models.CharField(max_length=64, blank=True)
    reminder_fingerprint = models.CharField(max_length=64, blank=True)
    last_status = models.CharField(max_length=12, blank=True)
    attempted_at = models.DateTimeField(null=True, blank=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    reminded_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Auftrittshinweis {self.pk}"


class GuestAccess(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    assignment = models.OneToOneField(
        Assignment, on_delete=models.CASCADE, related_name="guest_access"
    )
    nonce = models.UUIDField(default=uuid.uuid4)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    auto_notify = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Gastmusikerzugang {self.pk}"


class PerformanceAccount(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    performance = models.OneToOneField(Performance, on_delete=models.PROTECT)
    fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    travel = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    extras = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    note = EncryptedCharField(max_length=2000, blank=True, strict=True)
    invoice = models.OneToOneField(
        "billing.Invoice", on_delete=models.PROTECT, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    date = models.DateField(default=timezone.localdate)

    def __str__(self):
        return f"Auftrittsabrechnung {self.pk}"


class FeeTemplate(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    name = models.CharField(max_length=150)
    fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    allowance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(fee__gte=0, allowance__gte=0),
                name="music_fee_template_nonnegative",
            )
        ]

    def __str__(self):
        return self.name


class MusicianClaim(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    assignment = models.OneToOneField(Assignment, on_delete=models.PROTECT)
    fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    allowance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    expenses = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    attended = models.BooleanField(default=False)
    note = EncryptedCharField(max_length=2000, blank=True, strict=True)
    status = models.CharField(max_length=10, default="draft")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    approved_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Musikerabrechnung {self.pk}"


class PerformanceExpense(models.Model):
    """Jede tatsächliche Ausgabe wird einmal einem Auftritt zugeordnet."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    account = models.ForeignKey(
        PerformanceAccount, on_delete=models.PROTECT, related_name="payments"
    )
    claim = models.ForeignKey(
        MusicianClaim, on_delete=models.PROTECT, null=True, blank=True, related_name="payments"
    )
    booking = models.OneToOneField(
        "finance.Booking", on_delete=models.PROTECT, related_name="performance_expense"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Auftrittsausgabe {self.pk}"


class PreviousPerformanceInvoice(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    account = models.ForeignKey(
        PerformanceAccount, on_delete=models.PROTECT, related_name="previous_invoices"
    )
    invoice = models.OneToOneField("billing.Invoice", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Frühere Auftrittsrechnung {self.pk}"


class Equipment(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    item = models.OneToOneField(
        "materials.MaterialItem", on_delete=models.CASCADE, related_name="music_equipment"
    )
    kind = models.CharField(
        max_length=12, choices=[("instrument", "instrument"), ("uniform", "uniform")]
    )
    instrument = models.CharField(max_length=100, blank=True)
    size = models.CharField(max_length=100, blank=True)
    maintenance_due = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"Musikausstattung {self.pk}"


class EquipmentLoan(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name="loans")
    musician = models.ForeignKey(Musician, on_delete=models.PROTECT)
    issued_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateField()
    returned_at = models.DateTimeField(null=True, blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    returned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    location_before = EncryptedJSONField(default=dict)
    issue_condition = models.CharField(max_length=15)
    return_condition = models.CharField(max_length=15, blank=True)
    note = EncryptedCharField(max_length=1000, blank=True, strict=True)
    return_note = EncryptedCharField(max_length=1000, blank=True, strict=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["equipment"],
                condition=models.Q(returned_at__isnull=True),
                name="music_equipment_one_open_loan",
            )
        ]

    def __str__(self):
        return f"Musikausgabe {self.pk}"


class EquipmentMaintenance(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name="maintenance")
    date = models.DateField()
    next_due = models.DateField(null=True, blank=True)
    condition = models.CharField(max_length=15)
    note = EncryptedCharField(max_length=1000, blank=True, strict=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Musikwartung {self.pk}"


class Piece(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    composer = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.title


class Arrangement(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    piece = models.ForeignKey(Piece, on_delete=models.PROTECT)
    name = models.CharField(max_length=200)
    arranger = models.CharField(max_length=200, blank=True)
    publisher = models.CharField(max_length=200, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    difficulty = models.CharField(max_length=100, blank=True)
    ensemble = models.CharField(max_length=200, blank=True)
    license_note = models.CharField(max_length=2000, blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class ScorePart(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    arrangement = models.ForeignKey(Arrangement, on_delete=models.PROTECT, related_name="parts")
    instrument = models.CharField(max_length=100)
    register = models.CharField(max_length=100, blank=True)
    kind = models.CharField(max_length=10, default="part")
    paper_format = models.CharField(max_length=10, default="concert")
    required_players = models.PositiveSmallIntegerField(default=1)
    copies = models.PositiveSmallIntegerField(default=0)
    location = models.CharField(max_length=300, blank=True)

    def __str__(self):
        return self.instrument


class ScoreDocument(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    arrangement = models.ForeignKey(Arrangement, on_delete=models.CASCADE)
    part = models.ForeignKey(ScorePart, on_delete=models.SET_NULL, null=True, blank=True)
    document = models.ForeignKey("documents.Document", on_delete=models.SET_NULL, null=True)
    usage_note = models.CharField(max_length=2000, blank=True)

    def __str__(self):
        return f"Notenunterlage {self.pk}"


class ProgramEntry(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    performance = models.ForeignKey(
        Performance, on_delete=models.CASCADE, related_name="program_entries"
    )
    arrangement = models.ForeignKey(Arrangement, on_delete=models.PROTECT, null=True, blank=True)
    position = models.PositiveIntegerField(default=1)
    kind = models.CharField(max_length=10, default="piece")
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    paper_format = models.CharField(max_length=10, default="concert")
    note = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self):
        return f"Programmpunkt {self.pk}"


class Rehearsal(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    event = models.OneToOneField("events.Event", on_delete=models.PROTECT)
    focus = models.CharField(max_length=2000, blank=True)
    remind_days = models.PositiveSmallIntegerField(default=1)

    def __str__(self):
        return f"Probe {self.pk}"


class RehearsalItem(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    rehearsal = models.ForeignKey(Rehearsal, on_delete=models.CASCADE, related_name="items")
    arrangement = models.ForeignKey(Arrangement, on_delete=models.PROTECT)
    focus = models.CharField(max_length=500, blank=True)

    def __str__(self):
        return f"Probenstück {self.pk}"


class RehearsalProgram(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    rehearsal = models.ForeignKey(Rehearsal, on_delete=models.CASCADE, related_name="programs")
    original_start = models.DateTimeField()
    focus = models.CharField(max_length=2000, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["rehearsal", "original_start"], name="probe_programm_einmal"
            )
        ]

    def __str__(self):
        return f"Einzelprobenprogramm {self.pk}"


class RehearsalProgramItem(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    program = models.ForeignKey(RehearsalProgram, on_delete=models.CASCADE, related_name="items")
    arrangement = models.ForeignKey(Arrangement, on_delete=models.PROTECT)
    position = models.PositiveSmallIntegerField()
    focus = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["position", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["program", "position"], name="probe_programm_position")
        ]

    def __str__(self):
        return f"Einzelprobenstück {self.pk}"


class RehearsalInvitation(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    rehearsal = models.ForeignKey(Rehearsal, on_delete=models.PROTECT, related_name="invitations")
    musician = models.ForeignKey(Musician, on_delete=models.PROTECT)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["rehearsal", "musician"], name="probe_einladung_einmal")
        ]

    def __str__(self):
        return f"Probeneinteilung {self.pk}"


class RehearsalResponse(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    invitation = models.ForeignKey(
        RehearsalInvitation, on_delete=models.PROTECT, related_name="responses"
    )
    original_start = models.DateTimeField()
    status = models.CharField(max_length=10)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["invitation", "original_start"], name="probe_rueckmeldung_einmal"
            )
        ]

    def __str__(self):
        return f"Probenrückmeldung {self.pk}"


class ScoreLoan(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    part = models.ForeignKey(ScorePart, on_delete=models.PROTECT, related_name="loans")
    musician = models.ForeignKey(Musician, on_delete=models.PROTECT)
    quantity = models.PositiveSmallIntegerField()
    returned = models.PositiveSmallIntegerField(default=0)
    issued_on = models.DateField(default=timezone.localdate)
    due_on = models.DateField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0, returned__lte=models.F("quantity")),
                name="notenausgabe_menge_gueltig",
            )
        ]

    def __str__(self):
        return f"Notenausgabe {self.pk}"


class ScoreReturn(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    loan = models.ForeignKey(ScoreLoan, on_delete=models.PROTECT, related_name="returns")
    quantity = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="notenrueckgabe_positiv"
            )
        ]

    def __str__(self):
        return f"Notenrückgabe {self.pk}"


class RehearsalNotice(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    invitation = models.ForeignKey(RehearsalInvitation, on_delete=models.CASCADE)
    original_start = models.DateTimeField()
    kind = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["invitation", "original_start", "kind"], name="probe_hinweis_einmal"
            )
        ]

    def __str__(self):
        return f"Probenhinweis {self.pk}"
