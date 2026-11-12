"""Fristenkalender: wiederkehrende Pflichten einer Einheit (Funktionsvorschläge 12.11., Punkt 5).

Eine Pflicht hat eine nächste Frist und wiederholt sich alle ``interval_months`` Monate
(leer: einmalig). Zuständig ist eine Rolle der Einheit, nicht eine Person: Nach einem
Vorstandswechsel erinnert HUBIplan die neuen Inhaber. Pflichten mit dem Auslöser „Wahl“
haben keine Frist; nach jeder Wahl in ein vertretungsberechtigtes Amt entsteht eine Aufgabe.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


class Obligation(models.Model):
    class Trigger(models.TextChoices):
        DATE = "date", _("Frist")
        ELECTION = "election", _("nach einer Vorstandswahl")

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    # Kennung des Vorschlags, aus dem die Pflicht übernommen wurde (leer: selbst angelegt)
    key = models.CharField(max_length=40, blank=True)
    title = models.CharField(_("Bezeichnung"), max_length=200)
    note = models.TextField(_("Hinweis"), blank=True)
    trigger = models.CharField(max_length=10, choices=Trigger.choices, default=Trigger.DATE)
    due_date = models.DateField(_("Nächste Frist"), null=True, blank=True)
    interval_months = models.PositiveSmallIntegerField(_("Wiederholung in Monaten"), null=True)
    remind_days = models.PositiveSmallIntegerField(_("Erinnerung Tage vorher"), default=30)
    # Auslöser „Wahl“: Frist der Aufgabe in Tagen nach der Versammlung
    days_after = models.PositiveSmallIntegerField(default=14)
    role = models.ForeignKey(
        "access.Role", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    active = models.BooleanField(default=True)
    # Frist, zu der die Erinnerungsmail verschickt ist (einmal je Frist)
    reminded_for = models.DateField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date", "title", "pk"]
        indexes = [models.Index(fields=["organization", "active", "due_date"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(trigger="election") | Q(due_date__isnull=False) | Q(active=False),
                name="obligation_date_needs_due",
            ),
            models.CheckConstraint(
                condition=Q(interval_months__isnull=True) | Q(interval_months__gte=1),
                name="obligation_interval_positive",
            ),
        ]

    def __str__(self):
        return self.title


class ObligationDone(models.Model):
    """Nachweis: wann welche Frist einer Pflicht erledigt wurde."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    obligation = models.ForeignKey(Obligation, on_delete=models.CASCADE, related_name="history")
    due_date = models.DateField(null=True, blank=True)
    done_on = models.DateField()
    note = models.TextField(blank=True)
    done_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-done_on", "-pk"]

    def __str__(self):
        return f"{self.obligation_id}: {self.done_on}"
