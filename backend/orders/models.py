"""Sammelbestellungen im Verein (Lückenliste 20.11.2026, Punkt B4).

Der Vorstand legt eine Sammelbestellung mit Artikeln an, etwa Vereinskleidung, Festschrift oder
Uniformteile, je Artikel wahlweise mit Größen oder Varianten, Preis und Höchstmenge. Mitglieder
bestellen bis zur Frist im Mitgliederbereich oder in der App und können bis dahin ändern. Die
Verwaltung sieht die Summen je Artikel und Größe für die Bestellung beim Lieferanten, legt auf
Wunsch je Bestellung eine Rechnung an und hakt die Ausgabe ab.

Preis und Rechnung sind freiwillig (Ralf 21.11.2026): Eine reine Größenabfrage hat Artikel ohne
Preis; zahlt der Verein, steht ``club_pays`` und es entsteht nie eine Rechnung.
"""

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.encfields import EncryptedCharField

MAX_ARTICLES = 30
MAX_VARIANTS = 30
MAX_QUANTITY = 99


class OrderCampaign(models.Model):
    """Eine Sammelbestellung mit Frist, an den Verein oder eine Untereinheit gerichtet."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    # Wer bestellen darf: alle aktuellen Mitglieder des Vereins oder nur dieser Untereinheit
    department = models.ForeignKey(
        "organizations.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    title = models.CharField(_("Titel"), max_length=200)
    text = models.TextField(_("Beschreibung"), blank=True)
    # Bestellen und Ändern bis einschließlich zu diesem Tag
    deadline = models.DateField(_("Bestellen bis"))
    # Verein übernimmt die Kosten: Preise nur für die Verwaltung, keine Rechnung
    club_pays = models.BooleanField(default=False)
    payment_category = models.ForeignKey(
        "finance.Category", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    # Leer: Entwurf, Mitglieder sehen nichts
    published_at = models.DateTimeField(null=True, blank=True)
    # Vor der Frist beendet oder nach der Frist abgeschlossen
    closed_at = models.DateTimeField(null=True, blank=True)
    push = models.BooleanField(default=False)
    pushed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-deadline", "-pk"]
        indexes = [models.Index(fields=["organization", "deadline"])]

    def __str__(self):
        return f"order campaign {self.pk}"


class OrderArticle(models.Model):
    """Artikel einer Sammelbestellung, z. B. Poloshirt (S–XXL, 25 €) oder Festschrift."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    campaign = models.ForeignKey(OrderCampaign, on_delete=models.CASCADE, related_name="articles")
    name = models.CharField(_("Name"), max_length=100)
    text = models.CharField(_("Hinweis"), max_length=300, blank=True)
    # Leer: ohne Preis (Größenabfrage oder der Verein zahlt)
    price = models.DecimalField(
        _("Preis"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    # Größen oder Varianten zur Auswahl, z. B. ["S", "M", "L"]; leer: keine Auswahl
    variants = models.JSONField(default=list, blank=True)
    # Überschrift der Auswahl, z. B. „Größe“ oder „Farbe“
    variant_label = models.CharField(max_length=40, blank=True)
    max_per_member = models.PositiveSmallIntegerField(null=True, blank=True)
    max_total = models.PositiveIntegerField(null=True, blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self):
        return self.name


class MemberOrder(models.Model):
    """Bestellung eines Mitglieds in einer Sammelbestellung (eine je Mitglied)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    campaign = models.ForeignKey(OrderCampaign, on_delete=models.CASCADE, related_name="orders")
    membership = models.ForeignKey("members.Membership", on_delete=models.CASCADE, related_name="+")
    note = EncryptedCharField(max_length=500, blank=True)
    invoice = models.ForeignKey(
        "billing.Invoice", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    handed_out_at = models.DateTimeField(null=True, blank=True)
    # Von der Verwaltung eingetragen (z. B. von einer Papierliste)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "membership"], name="orders_one_per_member"
            ),
        ]

    def __str__(self):
        return f"member order {self.pk}"


class MemberOrderLine(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    order = models.ForeignKey(MemberOrder, on_delete=models.CASCADE, related_name="lines")
    article = models.ForeignKey(OrderArticle, on_delete=models.RESTRICT, related_name="lines")
    variant = models.CharField(max_length=60, blank=True)
    quantity = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        ordering = ["article__position", "article_id", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["order", "article", "variant"], name="orders_line_once"
            ),
        ]

    def __str__(self):
        return f"order line {self.pk}"
