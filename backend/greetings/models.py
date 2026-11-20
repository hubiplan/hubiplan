"""Glückwünsche zu Geburtstag und Mitgliedsjubiläum.

Die Einstellung je Verein (``GreetingSettings``) legt fest, wem gratuliert wird und mit
welchem Text. Einige Tage vorher entsteht je Tag und Anlass ein Rundschreiben der Art
„Glückwunsch“ als Entwurf (``GreetingBatch``): So lassen sich Briefe an Mitglieder ohne
E-Mail rechtzeitig drucken. Am Tag selbst geht es per App oder Mail hinaus, entweder von
selbst oder erst nach Freigabe. Mitglieder können widersprechen
(``Membership.greetings_opt_out_at``).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy

DEFAULT_ROUND_AGES = "18, 30, 40, 50, 60, 65, 70, 75"
MAX_LEAD_DAYS = 30


class GreetingSettings(models.Model):
    class Birthdays(models.TextChoices):
        OFF = "off", gettext_lazy("keine")
        ROUND = "round", gettext_lazy("nur zu besonderen Geburtstagen")
        ALL = "all", gettext_lazy("zu jedem Geburtstag")

    organization = models.OneToOneField(
        "organizations.Organization", on_delete=models.CASCADE, related_name="greeting_settings"
    )
    birthdays = models.CharField(max_length=6, choices=Birthdays.choices, default=Birthdays.OFF)
    # Besondere Geburtstage, durch Komma getrennt; ab ``every_year_from`` jedes Jahr (0 = nie)
    round_ages = models.CharField(max_length=200, blank=True, default=DEFAULT_ROUND_AGES)
    every_year_from = models.PositiveSmallIntegerField(default=80)
    jubilees = models.BooleanField(default=False)
    # Vorstand gibt jeden Glückwunsch selbst frei, statt dass er von selbst hinausgeht
    approval = models.BooleanField(default=False)
    # So viele Tage vorher entsteht der Entwurf (Briefe drucken)
    lead_days = models.PositiveSmallIntegerField(default=7)
    # Ab dieser Stunde des Tages wird versendet
    send_hour = models.PositiveSmallIntegerField(default=9)
    via_app = models.BooleanField(default=True)
    also_mail = models.BooleanField(default=False)
    birthday_subject = models.CharField(max_length=200, blank=True, default="")
    birthday_body = models.TextField(max_length=5000, blank=True, default="")
    jubilee_subject = models.CharField(max_length=200, blank=True, default="")
    jubilee_body = models.TextField(max_length=5000, blank=True, default="")
    reply_to = models.EmailField(blank=True, default="")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Einstellung für Glückwünsche")

    def __str__(self) -> str:
        return f"Glückwünsche {self.organization_id}"

    @property
    def active(self) -> bool:
        return self.birthdays != self.Birthdays.OFF or self.jubilees


class GreetingBatch(models.Model):
    """Glückwünsche eines Vereins zu einem Anlass an einem Tag (ein Rundschreiben)."""

    class Kind(models.TextChoices):
        BIRTHDAY = "birthday", gettext_lazy("Geburtstag")
        JUBILEE = "jubilee", gettext_lazy("Jubiläum")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    date = models.DateField()
    kind = models.CharField(max_length=10, choices=Kind.choices)
    circular = models.OneToOneField(
        "circulars.Circular",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="greeting_batch",
    )
    # Vom Vorstand ausgelassen oder ohne Empfänger: kommt nicht wieder
    skipped_at = models.DateTimeField(null=True, blank=True)
    skipped_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    note = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "kind"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "date", "kind"], name="glueckwunsch_je_tag_und_anlass"
            )
        ]

    def __str__(self) -> str:
        return f"Glückwunsch {self.get_kind_display()} {self.date:%d.%m.%Y}"
