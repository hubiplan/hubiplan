"""Ermäßigung mit Nachweis (docs/beitragsnachweise.md).

Eine Beitragsordnung gewährt manchen Mitgliedern eine Ermäßigung nur gegen einen jährlichen
Nachweis bis zu einer Frist (z. B. Studierende: Immatrikulationsbescheinigung bis 28.02.).
Fehlt er nach Frist und Kulanzzeit, zahlt das Mitglied für dieses Beitragsjahr den normalen
Beitrag seiner Mitgliedsart. Die Art bleibt dabei unverändert.

- ``ProofDiscount``: die Ermäßigung des Vereins mit Frist, Kulanzzeit und Erinnerungen
- ``DiscountAssignment``: welches Mitglied die Ermäßigung von wann bis wann beansprucht
- ``FeeProof``: ein eingereichter Nachweis für ein Beitragsjahr samt Prüfung
- ``ProofNotice``: welche Erinnerung oder Mitteilung schon verschickt wurde
- ``ProofLink``: persönlicher Link zum Einreichen ohne Zugang
- ``ProofSettings``: automatische Anerkennung nach grüner Vorprüfung

Die Datei eines Nachweises wird gelöscht, sobald er entschieden ist; es bleibt der Vermerk
(Art, gültig bis, wer und wann geprüft hat).
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.encfields import EncryptedCharField, EncryptedJSONField
from core.privatefiles import PrivateFileField
from exchange.models import private_storage

DEFAULT_KINDS = [
    "Immatrikulationsbescheinigung",
    "Bestätigung der Annahme als Doktorand/in",
    "Vergleichbarer Nachweis",
]


def default_kinds() -> list[str]:
    return list(DEFAULT_KINDS)


def file_path(instance, filename: str) -> str:
    stamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
    return f"feeproofs/{instance.organization_id}/{stamp}-{filename}"


class ProofDiscount(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    name = models.CharField(_("Bezeichnung"), max_length=100)
    member_type = models.ForeignKey(
        "members.MemberType",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("nur für Mitgliedsart"),
    )
    amount = models.DecimalField(
        _("ermäßigter Jahresbeitrag"), max_digits=10, decimal_places=2, null=True, blank=True
    )
    discount_percent = models.DecimalField(
        _("Abschlag in Prozent"), max_digits=5, decimal_places=2, null=True, blank=True
    )
    # Frist im Beitragsjahr (Tag und Monat, z. B. 28.02.)
    deadline_month = models.PositiveSmallIntegerField(
        default=2, validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    deadline_day = models.PositiveSmallIntegerField(
        default=28, validators=[MinValueValidator(1), MaxValueValidator(31)]
    )
    # Nachweise in so vielen Tagen nach der Frist zählen noch wie fristgerechte
    grace_days = models.PositiveSmallIntegerField(
        _("Kulanzzeit in Tagen"), null=True, blank=True, validators=[MaxValueValidator(365)]
    )
    # Wer im Beitragsjahr eintritt oder die Ermäßigung erst bekommt: so viele Tage zum Nachreichen
    late_join_days = models.PositiveSmallIntegerField(
        _("Nachreichen nach Beginn in Tagen"), default=28, validators=[MaxValueValidator(365)]
    )
    # Erste Erinnerung an einem festen Tag (leer: keine)
    remind_month = models.PositiveSmallIntegerField(
        null=True, blank=True, default=1, validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    remind_day = models.PositiveSmallIntegerField(
        null=True, blank=True, default=15, validators=[MinValueValidator(1), MaxValueValidator(31)]
    )
    # Zweite Erinnerung so viele Tage vor der Frist (leer: keine)
    remind_before_days = models.PositiveSmallIntegerField(
        null=True, blank=True, default=14, validators=[MaxValueValidator(120)]
    )
    # Nach Frist und Kulanzzeit Mitteilung „regulärer Beitrag“
    notify_after = models.BooleanField(default=True)
    kinds = models.JSONField(_("Arten von Nachweisen"), default=default_kinds, blank=True)
    is_archived = models.BooleanField(_("nicht mehr verwendet"), default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Ermäßigung mit Nachweis")
        verbose_name_plural = _("Ermäßigungen mit Nachweis")
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"], name="ermaessigung_name_je_verein"
            ),
            models.CheckConstraint(
                condition=Q(amount__isnull=True) ^ Q(discount_percent__isnull=True),
                name="ermaessigung_betrag_oder_prozent",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        from core.reorder import append_if_new

        append_if_new(
            self, "sort_order", ProofDiscount.objects.filter(organization_id=self.organization_id)
        )
        super().save(*args, **kwargs)


class DiscountAssignment(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    membership = models.ForeignKey(
        "members.Membership", on_delete=models.CASCADE, related_name="proof_discounts"
    )
    discount = models.ForeignKey(
        ProofDiscount, on_delete=models.PROTECT, related_name="assignments"
    )
    valid_from = models.DateField(_("von"))
    valid_until = models.DateField(_("bis"), null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-valid_from", "-pk"]
        indexes = [models.Index(fields=["organization", "membership"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(valid_until__isnull=True) | Q(valid_until__gte=F("valid_from")),
                name="ermaessigung_zeitraum",
            )
        ]

    def __str__(self) -> str:
        return f"{self.discount_id} ab {self.valid_from}"

    def covers(self, day) -> bool:
        return self.valid_from <= day and (self.valid_until is None or self.valid_until >= day)


class FeeProof(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", _("eingegangen")
        QUESTION = "question", _("Rückfrage")
        ACCEPTED = "accepted", _("anerkannt")
        REJECTED = "rejected", _("abgelehnt")

    class Channel(models.TextChoices):
        PORTAL = "portal", _("Mitgliederbereich")
        APP = "app", _("App")
        LINK = "link", _("persönlicher Link")
        MAIL = "mail", _("E-Mail")
        APPLICATION = "application", _("Mitgliedsantrag")
        BOARD = "board", _("vom Vorstand eingetragen")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    membership = models.ForeignKey(
        "members.Membership", on_delete=models.CASCADE, related_name="fee_proofs"
    )
    discount = models.ForeignKey(ProofDiscount, on_delete=models.PROTECT, related_name="proofs")
    year = models.PositiveSmallIntegerField(_("Beitragsjahr"))
    kind = models.CharField(_("Art des Nachweises"), max_length=100, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RECEIVED)
    channel = models.CharField(max_length=12, choices=Channel.choices)
    received_on = models.DateField(_("eingegangen am"))
    valid_until = models.DateField(_("gültig bis"), null=True, blank=True)
    # Datei bis zur Entscheidung, danach gelöscht (nur Vermerk bleibt)
    file = PrivateFileField(storage=private_storage, upload_to=file_path, blank=True)
    file_name = models.CharField(max_length=200, blank=True)
    content_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    file_deleted_at = models.DateTimeField(null=True, blank=True)
    # Ergebnis der automatischen Vorprüfung (Ampel, Gründe, Vorschlag „gültig bis“)
    precheck = EncryptedJSONField(default=dict, blank=True, strict=True)
    # Nachricht des Mitglieds beim Einreichen
    member_note = EncryptedCharField(max_length=500, blank=True)
    # Begründung einer Ablehnung oder Text der Rückfrage (geht an das Mitglied)
    note = EncryptedCharField(max_length=500, blank=True)
    # In der Kulanzzeit eingegangen
    late = models.BooleanField(default=False)
    # Nach Frist und Kulanzzeit im Einzelfall anerkannt
    outside_deadline = models.BooleanField(default=False)
    auto_accepted = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Beitragsnachweis")
        verbose_name_plural = _("Beitragsnachweise")
        ordering = ["-received_on", "-pk"]
        indexes = [
            models.Index(fields=["organization", "year", "status"]),
            models.Index(fields=["organization", "membership"]),
        ]

    def __str__(self) -> str:
        return f"{self.discount_id}/{self.year}"


class ProofNotice(models.Model):
    class Kind(models.TextChoices):
        FIRST = "first", _("erste Erinnerung")
        SECOND = "second", _("zweite Erinnerung")
        AFTER = "after", _("Mitteilung nach Fristablauf")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    membership = models.ForeignKey("members.Membership", on_delete=models.CASCADE, related_name="+")
    discount = models.ForeignKey(ProofDiscount, on_delete=models.CASCADE, related_name="+")
    year = models.PositiveSmallIntegerField()
    kind = models.CharField(max_length=10, choices=Kind.choices)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["membership", "discount", "year", "kind"], name="nachweis_hinweis_einmal"
            )
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.year}"


class ProofLink(models.Model):
    """Persönlicher Link aus der Erinnerungsmail: Nachweis ohne Zugang hochladen."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    membership = models.ForeignKey("members.Membership", on_delete=models.CASCADE, related_name="+")
    discount = models.ForeignKey(ProofDiscount, on_delete=models.CASCADE, related_name="+")
    year = models.PositiveSmallIntegerField()
    token_hash = models.CharField(max_length=64, unique=True)
    # Kennung der persönlichen Antwortadresse (rechnung+nw<Kennung>@…): Anhänge einer Antwort
    # auf die Erinnerung landen ohne Zuordnung von Hand beim richtigen Mitglied
    mail_key = models.CharField(max_length=20, unique=True)
    valid_until = models.DateField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Nachweis-Link {self.year}"


class ProofSettings(models.Model):
    organization = models.OneToOneField(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    # Nachweise mit grüner Vorprüfung ohne Menschen anerkennen
    auto_accept = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Beitragsnachweise {self.organization_id}"


class ApplicationProof(models.Model):
    """Nachweis zum Online-Mitgliedsantrag, bis zur Aufnahme (dann ``FeeProof``)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    application = models.ForeignKey(
        "admission.Application", on_delete=models.CASCADE, related_name="fee_proofs"
    )
    discount = models.ForeignKey(ProofDiscount, on_delete=models.CASCADE, related_name="+")
    file = PrivateFileField(storage=private_storage, upload_to=file_path, blank=True)
    file_name = models.CharField(max_length=200, blank=True)
    content_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    precheck = EncryptedJSONField(default=dict, blank=True, strict=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self) -> str:
        return self.file_name
