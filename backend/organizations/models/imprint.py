"""Einheiten: Impressum, soziale Medien und Adressen der Instanz."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext, gettext_lazy

from .organization import Organization


def new_imprint_key() -> str:
    import secrets

    return secrets.token_urlsafe(6)


class Imprint(models.Model):
    """Impressum und Datenschutzhinweise einer Einheit oder der Plattform.

    Leere Felder werden aus den Stammdaten der Einheit ergänzt (Name, Anschrift,
    Kontakt) und bei den Vertretungsberechtigten aus den Rollen mit dem Kennzeichen
    „vertritt die Einheit“. Wie das Impressum nach außen aussieht, berechnet
    ``organizations.imprint``.
    """

    class Mode(models.TextChoices):
        INHERIT = "inherit", gettext_lazy("von der übergeordneten Einheit übernehmen")
        OWN = "own", gettext_lazy("eigenes Impressum")
        LINK = "link", gettext_lazy("auf eigenes Impressum verlinken")

    class PrivacyMode(models.TextChoices):
        TEXT = "text", gettext_lazy("Text in HUBIplan")
        LINK = "link", gettext_lazy("auf eigene Seite verlinken")

    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name="imprint"
    )
    # Fester Teil der öffentlichen Adresse (/impressum/<key>); ändert sich nie
    public_key = models.CharField(max_length=20, unique=True, default=new_imprint_key)
    mode = models.CharField("Impressum", max_length=10, choices=Mode.choices)
    external_url = models.URLField("Adresse des eigenen Impressums", blank=True)
    name = models.CharField(
        "Name bzw. Firma", max_length=200, blank=True, help_text="Leer: Name der Einheit."
    )
    legal_form = models.CharField(
        "Rechtsform", max_length=100, blank=True, help_text="z. B. eingetragener Verein"
    )
    street = models.CharField("Straße und Hausnummer", max_length=200, blank=True)
    address_extra = models.CharField(
        "Adresszusatz",
        max_length=200,
        blank=True,
        default="",
        db_default="",
        help_text="z. B. c/o Firma oder Gebäude; steht über Straße und Hausnummer.",
    )
    postal_code = models.CharField("PLZ", max_length=10, blank=True)
    city = models.CharField("Ort", max_length=100, blank=True)
    representatives = models.TextField(
        "Vertretungsberechtigt",
        blank=True,
        help_text="Leer: aus den Rollen mit dem Kennzeichen „vertritt die Einheit“.",
    )
    email = models.EmailField("E-Mail", blank=True)
    phone = models.CharField("Telefon", max_length=50, blank=True)
    # Nur eingetragene Einheiten (e.V., bei der Plattform z. B. GmbH) haben
    # Registerangaben; dann gehören Registergericht und -nummer ins Impressum.
    registered = models.BooleanField(
        "im Register eingetragen",
        default=False,
        help_text="z. B. eingetragener Verein (e.V.) im Vereinsregister",
    )
    register_court = models.CharField("Registergericht", max_length=100, blank=True)
    register_number = models.CharField("Registernummer", max_length=50, blank=True)
    vat_id = models.CharField("Umsatzsteuer-Identifikationsnummer", max_length=30, blank=True)
    responsible = models.TextField(
        "Verantwortlich nach § 18 Abs. 2 MStV", blank=True, help_text="Name und Anschrift"
    )
    data_protection_officer = models.TextField("Datenschutzbeauftragte(r)", blank=True)
    extra_text = models.TextField("Weitere Angaben", blank=True)
    privacy_mode = models.CharField(
        "Datenschutzhinweise",
        max_length=10,
        choices=PrivacyMode.choices,
        default=PrivacyMode.TEXT,
    )
    # privacy_text ist der Entwurf; öffentlich gilt erst die veröffentlichte Fassung
    # (UI-Audit 29.10. NAF-02)
    privacy_text = models.TextField("Entwurf der Datenschutzhinweise", blank=True)
    privacy_published_text = models.TextField("Veröffentlichte Datenschutzhinweise", blank=True)
    privacy_published_at = models.DateTimeField("Datenschutzhinweise veröffentlicht am", null=True)
    privacy_url = models.URLField("Adresse der Datenschutzhinweise", blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Impressum"
        verbose_name_plural = "Impressen"

    def __str__(self) -> str:
        return f"Impressum {self.organization}"

    def clean(self) -> None:
        errors = {}
        if self.mode == self.Mode.LINK and not self.external_url:
            errors["external_url"] = gettext("Bitte die Adresse des Impressums angeben.")
        if self.mode == self.Mode.INHERIT and self.organization.type == Organization.Type.PLATFORM:
            errors["mode"] = gettext("Die Plattform braucht ein eigenes Impressum.")
        if self.privacy_mode == self.PrivacyMode.LINK and not self.privacy_url:
            errors["privacy_url"] = gettext("Bitte die Adresse der Datenschutzhinweise angeben.")
        if errors:
            raise ValidationError(errors)

    @staticmethod
    def default_mode(org: Organization) -> str:
        """Untereinheiten übernehmen, alle anderen haben ein eigenes Impressum."""
        if org.type == Organization.Type.UNIT:
            return Imprint.Mode.INHERIT
        return Imprint.Mode.OWN


class SocialLink(models.Model):
    """Social-Media-Kanal einer Einheit (Stammdaten, z. B. für Briefvorlage und Webseite)."""

    class Kind(models.TextChoices):
        FACEBOOK = "facebook", gettext_lazy("Facebook")
        INSTAGRAM = "instagram", gettext_lazy("Instagram")
        YOUTUBE = "youtube", gettext_lazy("YouTube")
        TIKTOK = "tiktok", gettext_lazy("TikTok")
        X = "x", gettext_lazy("X")
        MASTODON = "mastodon", gettext_lazy("Mastodon")
        BLUESKY = "bluesky", gettext_lazy("Bluesky")
        THREADS = "threads", gettext_lazy("Threads")
        WHATSAPP = "whatsapp", gettext_lazy("WhatsApp-Kanal")
        LINKEDIN = "linkedin", gettext_lazy("LinkedIn")
        OTHER = "other", gettext_lazy("Sonstiges")

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="social_links"
    )
    kind = models.CharField("Art", max_length=20, choices=Kind.choices)
    url = models.URLField("Adresse")
    label = models.CharField(
        "Anzeigename",
        max_length=100,
        blank=True,
        help_text="Kurz, z. B. @hubertus1920; leer: aus der Adresse.",
    )
    position = models.PositiveSmallIntegerField("Reihenfolge", default=0)

    class Meta:
        verbose_name = "Social-Media-Kanal"
        verbose_name_plural = "Social-Media-Kanäle"
        ordering = ["position", "pk"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.display}"

    @property
    def display(self) -> str:
        """Anzeigename oder die Adresse ohne https:// und www."""
        if self.label.strip():
            return self.label.strip()
        text = self.url.split("://", 1)[-1]
        text = text[4:] if text.startswith("www.") else text
        return text.rstrip("/")


class InstanceAddress(models.Model):
    """Weitere Adresse der Instanz für eine Einheit (White Label W7).

    Wer HUBIplan über diese Adresse aufruft, sieht auf der Anmeldeseite Name, Farben, Wappen
    und Symbol der Einheit; nach der Anmeldung ist sie vorausgewählt.
    """

    hostname = models.CharField("Adresse", max_length=253, unique=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="instance_addresses",
        verbose_name="Einheit",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["hostname"]
        verbose_name = "Adresse der Instanz"
        verbose_name_plural = "Adressen der Instanz"

    def __str__(self) -> str:
        return self.hostname
