"""Musikprofile und Besetzung ergänzen Mitglieder und Kalendereinträge."""

from django.db import models

from core.encfields import EncryptedCharField


class Musician(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    membership = models.OneToOneField(
        "members.Membership", on_delete=models.PROTECT, null=True, blank=True
    )
    name = EncryptedCharField(max_length=200, strict=True, blank=True)
    contact = EncryptedCharField(max_length=300, strict=True, blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name or f"Musiker {self.pk}"


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
