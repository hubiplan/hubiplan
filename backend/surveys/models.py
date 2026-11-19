"""Umfragen und Meinungsbilder (konzepte/umfragen-meinungsbilder.md).

Eine Umfrage gehört zu einem Verein oder einer Untereinheit (Spalte ``department``), auf Wunsch
zu einem Termin. Sie hat Fragen, jede Frage Antwortmöglichkeiten. Wer geantwortet hat, steht in
``SurveyParticipation``; was geantwortet wurde, in ``SurveyAnswer``. Bei einer anonymen Umfrage
verbindet nichts die beiden (wie bei der geheimen Online-Abstimmung der Versammlungen): Die
Antwort hat eine zufällige Nummer, keine Teilnahme und keinen Zeitpunkt.

Eine Umfrage beschließt nichts; förmliche Abstimmungen gehören zu den Versammlungen.
"""

import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.encfields import EncryptedCharField, EncryptedTextField

MAX_QUESTIONS = 10
MAX_OPTIONS = 30
# Anonymes Ergebnis erst ab so vielen Antworten (Fachfrage UM-7)
ANONYMOUS_MIN = 5


class Survey(models.Model):
    class Audience(models.TextChoices):
        MEMBERS = "members", _("Mitglieder")
        PERSONS = "persons", _("ausgewählte Personen")
        EVENT = "event", _("Eingeladene des Termins")
        EVENT_YES = "event_yes", _("wer zum Termin zugesagt hat")

    class Names(models.TextChoices):
        OPEN = "open", _("offen für alle Befragten")
        MANAGERS = "managers", _("nur für die Verwaltung")
        ANONYMOUS = "anonymous", _("anonym")

    class Results(models.TextChoices):
        AFTER_ANSWER = "after_answer", _("nach der eigenen Antwort")
        ALWAYS = "always", _("immer")
        AFTER_CLOSE = "after_close", _("nach dem Ende")
        MANAGERS = "managers", _("nur für die Verwaltung")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Entwurf")
        OPEN = "open", _("läuft")
        CLOSED = "closed", _("beendet")

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    department = models.ForeignKey(
        "organizations.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    event = models.ForeignKey(
        "events.Event", null=True, blank=True, on_delete=models.SET_NULL, related_name="surveys"
    )
    title = EncryptedCharField(_("Titel"), max_length=200)
    description = EncryptedTextField(_("Beschreibung"), blank=True)
    audience = models.CharField(max_length=10, choices=Audience.choices, default=Audience.MEMBERS)
    # Filter wie bei Rundschreiben: departments, member_types, roles, board, age_min, age_max
    filters = models.JSONField(default=dict, blank=True)
    # Ausgewählte Personen (Mitgliedschaften), nur bei audience=persons
    persons = models.JSONField(default=list, blank=True)
    names = models.CharField(max_length=10, choices=Names.choices, default=Names.MANAGERS)
    results = models.CharField(max_length=12, choices=Results.choices, default=Results.AFTER_ANSWER)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    closes_at = models.DateTimeField(_("Ende"), null=True, blank=True)
    # Erinnerung so viele Tage vor dem Ende an alle ohne Antwort (leer: keine)
    remind_days = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(14)]
    )
    # Antworten mit Namen so viele Monate nach dem Ende löschen, Zahlen bleiben (UM-10)
    keep_months = models.PositiveSmallIntegerField(
        default=12, validators=[MinValueValidator(1), MaxValueValidator(60)]
    )
    opened_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    reminded_at = models.DateTimeField(null=True, blank=True)
    # Zahl der Befragten beim Ende
    invited = models.PositiveIntegerField(null=True, blank=True)
    # Nach dem Aufräumen: das Ergebnis als Zahlen (Teilnahmen und Antworten sind gelöscht)
    archived = models.JSONField(null=True, blank=True)
    purged_at = models.DateTimeField(null=True, blank=True)
    # Aus einer Terminfindung angelegter Termin
    follow_event = models.ForeignKey(
        "events.Event", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["organization", "department"]),
            models.Index(fields=["status", "closes_at"]),
        ]

    def __str__(self):
        return f"survey {self.pk}"

    @property
    def anonymous(self) -> bool:
        return self.names == self.Names.ANONYMOUS


class SurveyQuestion(models.Model):
    class Kind(models.TextChoices):
        SINGLE = "single", _("Einfachauswahl")
        MULTIPLE = "multiple", _("Mehrfachauswahl")
        YESNO = "yesno", _("Ja / Nein / Enthaltung")
        DATES = "dates", _("Terminfindung")
        QUANTITY = "quantity", _("Mengenauswahl")
        TEXT = "text", _("Freitext")

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="questions")
    position = models.PositiveSmallIntegerField(default=0)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    text = EncryptedTextField(_("Frage"))
    required = models.BooleanField(default=True)
    # Mehrfachauswahl: höchstens so viele; Mengenauswahl: höchstens so viele Stück zusammen
    max_choices = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(50)]
    )
    # Terminfindung: Antwort „Vielleicht“ erlaubt
    allow_maybe = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self):
        return f"question {self.pk}"


class SurveyOption(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    question = models.ForeignKey(SurveyQuestion, on_delete=models.CASCADE, related_name="options")
    position = models.PositiveSmallIntegerField(default=0)
    label = EncryptedCharField(_("Antwort"), max_length=200, blank=True)
    # Terminfindung: vorgeschlagener Termin
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    all_day = models.BooleanField(default=False)
    # Höchstens so viele Personen bzw. Stück (leer: unbegrenzt)
    capacity = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(100000)]
    )

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self):
        return f"option {self.pk}"


class SurveyParticipation(models.Model):
    """Dass ein Mitglied geantwortet hat. Bei anonymen Umfragen ohne Zeitpunkt."""

    class Source(models.TextChoices):
        MEMBER = "member", _("Mitglied")
        BOARD = "board", _("Verwaltung")
        LINK = "link", _("Mail-Link")

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="participations")
    # Leer, nachdem die Daten des Mitglieds gelöscht wurden (die Zählung bleibt)
    membership = models.ForeignKey(
        "members.Membership", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MEMBER)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["survey", "membership"],
                condition=models.Q(membership__isnull=False),
                name="survey_participation_once",
            )
        ]

    def __str__(self):
        return f"participation {self.pk}"


class SurveyAnswer(models.Model):
    """Eine Antwort. Anonym: zufällige Nummer, ohne Teilnahme, ohne Zeitpunkt."""

    class Value(models.TextChoices):
        YES = "yes", _("Ja")
        MAYBE = "maybe", _("Vielleicht")
        NO = "no", _("Nein")
        ABSTAIN = "abstain", _("Enthaltung")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(SurveyQuestion, on_delete=models.CASCADE, related_name="answers")
    option = models.ForeignKey(
        SurveyOption, null=True, blank=True, on_delete=models.CASCADE, related_name="answers"
    )
    participation = models.ForeignKey(
        SurveyParticipation,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    value = models.CharField(max_length=8, choices=Value.choices, blank=True)
    quantity = models.PositiveSmallIntegerField(default=1, validators=[MaxValueValidator(50)])
    text = EncryptedTextField(_("Text"), blank=True)

    class Meta:
        # Zufällige Nummer: keine Reihenfolge der Abgabe
        ordering = ["pk"]
        indexes = [models.Index(fields=["question", "option"])]

    def __str__(self):
        return f"answer {self.pk}"
