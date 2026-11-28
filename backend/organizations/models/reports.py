"""Einheiten: Rückmeldungen und Meldungen (Hilfe, CSP, Köder)."""

from __future__ import annotations

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy


class HelpFeedback(models.Model):
    """Antwort auf „Hat das geholfen?“ unter einer Anleitung oder Seitenhilfe.

    Bewusst ohne Person, Einheit und Adresse: nur der Hilfetext, die Sprache, die Fassung,
    Ja oder Nein, ein freiwilliger Satz und der Tag (docs/hilfe.md).
    """

    key = models.CharField("Hilfetext", max_length=80)
    language = models.CharField("Sprache", max_length=5)
    version = models.CharField("Fassung", max_length=40, blank=True)
    helpful = models.BooleanField("hat geholfen")
    comment = models.CharField("Was hat gefehlt?", max_length=300, blank=True)
    day = models.DateField("Tag")

    class Meta:
        ordering = ["-day", "-id"]
        indexes = [models.Index(fields=["key"], name="helpfeedback_key")]
        verbose_name = "Rückmeldung zur Hilfe"
        verbose_name_plural = "Rückmeldungen zur Hilfe"

    def __str__(self) -> str:
        return f"{self.key}: {'ja' if self.helpful else 'nein'}"


class HelpSearchMiss(models.Model):
    """Suchwörter der Hilfe ohne Treffer, gezählt je Sprache; ohne Person und Einheit."""

    term = models.CharField("Suchwörter", max_length=60)
    language = models.CharField("Sprache", max_length=5)
    count = models.PositiveIntegerField("Anzahl", default=1)
    last_day = models.DateField("zuletzt am")

    class Meta:
        ordering = ["-count", "term"]
        constraints = [
            models.UniqueConstraint(fields=["term", "language"], name="helpsearchmiss_einmalig")
        ]
        verbose_name = "Suche in der Hilfe ohne Treffer"
        verbose_name_plural = "Suchen in der Hilfe ohne Treffer"

    def __str__(self) -> str:
        return f"{self.term} ({self.count})"


class CspReport(models.Model):
    """Vom Browser gemeldeter Verstoß gegen die Inhaltsregeln (CSP) der Oberfläche.

    Gezählt je Regel, blockierter Herkunft und Seite; ohne Person, Einheit und Adresse des
    Aufrufers (docs/betrieb.md, „Meldungen des Browsers“).
    """

    directive = models.CharField("Regel", max_length=40)
    blocked = models.CharField("blockiert", max_length=120)
    page = models.CharField("Seite", max_length=120)
    count = models.PositiveIntegerField("Anzahl", default=1)
    first_day = models.DateField("zuerst am")
    last_day = models.DateField("zuletzt am")
    version = models.CharField("Fassung", max_length=40, blank=True)

    class Meta:
        ordering = ["-last_day", "-count", "directive"]
        constraints = [
            models.UniqueConstraint(
                fields=["directive", "blocked", "page"], name="cspreport_einmalig"
            )
        ]
        verbose_name = "Meldung des Browsers (CSP)"
        verbose_name_plural = "Meldungen des Browsers (CSP)"

    def __str__(self) -> str:
        return f"{self.directive} {self.blocked} ({self.count})"


class DecoyHit(models.Model):
    """Auslösung eines Köders (``organizations.decoys``): Jemand hat Köderdaten benutzt.

    Gezählt je Art, Köder, Angabe und Tag. Ohne Mandantentrennung, nur für die Plattform.
    """

    class Kind(models.TextChoices):
        MAIL_IN = "mail_in", gettext_lazy("Mail an die Köderadresse")
        MAIL_OUT = "mail_out", gettext_lazy("eigene Mail an die Köderadresse")
        LOGIN = "login", gettext_lazy("Anmeldeversuch")
        LOOKUP = "lookup", gettext_lazy("Abruf über die Schnittstelle")

    kind = models.CharField("Art", max_length=10, choices=Kind.choices)
    # Nummer der Köder-Mitgliedschaft; bewusst kein Fremdschlüssel (bleibt nach dem Löschen)
    membership_id = models.BigIntegerField("Köder", null=True, blank=True)
    detail = models.CharField("Angabe", max_length=200, blank=True)
    day = models.DateField("Tag")
    count = models.PositiveIntegerField("Anzahl", default=1)
    last_at = models.DateTimeField("zuletzt", default=timezone.now)

    class Meta:
        ordering = ["-last_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "membership_id", "detail", "day"], name="decoyhit_einmalig"
            )
        ]
        verbose_name = "Köder-Auslösung"
        verbose_name_plural = "Köder-Auslösungen"

    def __str__(self) -> str:
        return f"{self.kind} {self.day} ({self.count})"
