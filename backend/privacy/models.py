"""Datenschutz-Werkzeuge eines Vereins (Lückenliste 20.11.2026, B5).

- ``PrivacySettings``: Angaben für das Verzeichnis der Verarbeitungstätigkeiten (Art. 30
  DSGVO), die HUBIplan nicht kennt: Datenschutzbeauftragter, technische und organisatorische
  Maßnahmen, Betreiber der HUBIplan-Instanz, ausgeblendete Vorschläge.
- ``ProcessingActivity``: eigene Verarbeitungstätigkeiten neben den Vorschlägen aus den
  eingeschalteten Modulen (``catalog.py``).
- ``DataBreach``: Protokoll einer Datenpanne (Art. 33 Abs. 5 DSGVO) mit der 72-Stunden-Frist
  für die Meldung an die Aufsichtsbehörde und der Benachrichtigung Betroffener (Art. 34).

Auftragsverarbeiter sind Geschäftspartner mit der Rolle „Auftragsverarbeiter“, ihre Verträge
Vereinbarungen der Art „Auftragsverarbeitungsvertrag“ (billing).
"""

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.encfields import EncryptedTextField

REPORT_HOURS = 72


class PrivacySettings(models.Model):
    organization = models.OneToOneField(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    dpo_name = models.CharField(_("Datenschutzbeauftragte/r"), max_length=200, blank=True)
    dpo_contact = models.CharField(_("Kontakt"), max_length=300, blank=True)
    hoster = models.CharField(_("Betreiber der HUBIplan-Instanz"), max_length=300, blank=True)
    toms = models.TextField(_("Technische und organisatorische Maßnahmen"), blank=True)
    # Vorschläge aus dem Katalog, die nicht ins Verzeichnis sollen
    hidden_keys = models.JSONField(default=list, blank=True)
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )

    def __str__(self):
        return f"Datenschutz {self.organization_id}"


class ProcessingActivity(models.Model):
    """Eigene Verarbeitungstätigkeit (die Vorschläge stehen in ``catalog.py``)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    title = models.CharField(_("Bezeichnung"), max_length=200)
    purpose = models.TextField(_("Zweck"), blank=True)
    legal_basis = models.CharField(_("Rechtsgrundlage"), max_length=300, blank=True)
    subjects = models.CharField(_("Betroffene"), max_length=300, blank=True)
    categories = models.TextField(_("Datenkategorien"), blank=True)
    recipients = models.TextField(_("Empfänger"), blank=True)
    third_country = models.CharField(_("Übermittlung in Drittländer"), max_length=300, blank=True)
    retention = models.TextField(_("Löschfrist"), blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title", "pk"]

    def __str__(self):
        return self.title


class DataBreach(models.Model):
    """Protokoll einer Verletzung des Schutzes personenbezogener Daten."""

    class Risk(models.TextChoices):
        UNLIKELY = "unlikely", _("voraussichtlich kein Risiko")
        RISK = "risk", _("Risiko")
        HIGH = "high", _("hohes Risiko")

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    title = models.CharField(_("Kurzbezeichnung"), max_length=200)
    discovered_at = models.DateTimeField(_("Bekannt geworden"))
    occurred = models.CharField(_("Zeitpunkt oder Zeitraum der Panne"), max_length=200, blank=True)
    description = EncryptedTextField(_("Was ist passiert?"), max_length=5000, blank=True)
    categories = EncryptedTextField(_("Betroffene Daten"), max_length=2000, blank=True)
    affected = models.CharField(
        _("Betroffene Personen (Art, ungefähre Zahl)"), max_length=300, blank=True
    )
    consequences = EncryptedTextField(_("Wahrscheinliche Folgen"), max_length=3000, blank=True)
    measures = EncryptedTextField(_("Ergriffene Maßnahmen"), max_length=5000, blank=True)
    risk = models.CharField(max_length=10, choices=Risk.choices, default=Risk.RISK)
    reported_at = models.DateTimeField(_("Gemeldet an die Aufsichtsbehörde"), null=True, blank=True)
    report_reference = models.CharField(_("Aktenzeichen der Meldung"), max_length=100, blank=True)
    # Begründung, warum nicht (rechtzeitig) gemeldet wurde (Art. 33 Abs. 1 Satz 2)
    no_report_reason = EncryptedTextField(_("Begründung"), max_length=3000, blank=True)
    notified_at = models.DateTimeField(_("Betroffene benachrichtigt"), null=True, blank=True)
    closed_at = models.DateTimeField(_("Abgeschlossen"), null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )

    class Meta:
        ordering = ["-discovered_at", "-pk"]
        indexes = [models.Index(fields=["organization", "closed_at"])]

    def __str__(self):
        return self.title

    @property
    def report_deadline(self):
        return self.discovered_at + timedelta(hours=REPORT_HOURS)

    @property
    def needs_report(self) -> bool:
        return self.risk != self.Risk.UNLIKELY
