"""Inhalte der Webseite, die HUBIplan nicht aus der Vereinsverwaltung kennt:
Begrüßung, Textseiten (z. B. Geschichte), Kurztexte der Untereinheiten, Bilder.

Texte haben einen Entwurf und eine veröffentlichte Fassung. Sichtbar ist nur
die veröffentlichte (im Wartungsmodus auch die nur in der Vorschau). Jede
Veröffentlichung bleibt als Fassung erhalten und lässt sich zurückholen.
"""

from __future__ import annotations

import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy

from core.privatefiles import PrivateFileField
from exchange.models import private_storage

from .models import Website

# Bilderkarussell: Sekunden bis zum nächsten Bild
GALLERY_INTERVAL = 7
MIN_INTERVAL = 3
MAX_INTERVAL = 30

MAX_TITLE = 120
MAX_BODY = 50_000
# Zeitleiste der Chronik (Ralf 02.11.: keine Textwand): kurze Einträge mit Jahr
TIMELINE_SLUG = "geschichte"
MAX_TIMELINE = 300
MAX_TIMELINE_TITLE = 120
MAX_TIMELINE_TEXT = 400
MAX_TIMELINE_IMAGES = 6  # Bilder je Ereignis (Ralf 02.11.: z. B. drei Plakate)
SLUG_RE = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
# Adressen, die die Webseite selbst belegt
RESERVED_SLUGS = frozenset(
    {
        "vorstand",
        "termine",
        "zuege",
        "einheiten",
        "majestaeten",
        "chronik",
        "aemter",
        "kontakt",
        "impressum",
        "datenschutz",
        "vorschau",
        "bilder",
        "api",
        "static",
        "kalender",
    }
)


class WebsiteText(models.Model):
    class Kind(models.TextChoices):
        GREETING = "greeting", "Begrüßung (Startseite)"
        PAGE = "page", "Textseite"
        UNIT = "unit", "Text einer Untereinheit"

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    website = models.ForeignKey(Website, on_delete=models.CASCADE, related_name="texts")
    kind = models.CharField("Art", max_length=10, choices=Kind.choices)
    department = models.ForeignKey(
        "organizations.Department",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    slug = models.CharField("Adresse", max_length=60, blank=True)
    menu_position = models.PositiveSmallIntegerField("Reihenfolge im Menü", default=0)
    show_in_menu = models.BooleanField("im Menü zeigen", default=True)
    # Entwurf
    title = models.CharField("Titel", max_length=MAX_TITLE, blank=True)
    body = models.TextField("Text", max_length=MAX_BODY, blank=True)
    image = models.ForeignKey(
        "website.WebsiteImage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Bild",
    )
    # Bilderkarussell der Begrüßung: IDs der Bilder in ihrer Reihenfolge
    gallery = models.JSONField("Bilderkarussell", default=list, blank=True)
    # Sekunden bis zum nächsten Bild, je Karussell einstellbar (Ralf 01.11.)
    gallery_interval = models.PositiveSmallIntegerField(
        "Wechsel nach (Sekunden)",
        default=GALLERY_INTERVAL,
        validators=[MinValueValidator(MIN_INTERVAL), MaxValueValidator(MAX_INTERVAL)],
    )
    # Beginnt mit einem zufälligen Bild statt mit dem ersten der Liste
    gallery_random = models.BooleanField("zufälliges Startbild", default=False)
    # Bildunterschrift unter Bild und Karussell auf der Webseite zeigen (Ralf 02.11., Standard aus)
    show_captions = models.BooleanField("Bildunterschriften zeigen", default=False)
    # Zeitleiste der Chronik: [{"year", "until", "title", "text", "image"}]
    timeline = models.JSONField("Zeitleiste", default=list, blank=True)
    # Webseite zeigt die neuesten Einträge oben (Ralf 02.11., wahlweise)
    timeline_newest_first = models.BooleanField("neueste Einträge oben", default=False)
    # Veröffentlicht
    published_title = models.CharField(max_length=MAX_TITLE, blank=True)
    published_body = models.TextField(blank=True)
    published_image = models.ForeignKey(
        "website.WebsiteImage", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    published_gallery = models.JSONField(default=list, blank=True)
    published_gallery_interval = models.PositiveSmallIntegerField(default=GALLERY_INTERVAL)
    published_gallery_random = models.BooleanField(default=False)
    published_show_captions = models.BooleanField(default=False)
    published_timeline = models.JSONField(default=list, blank=True)
    published_timeline_newest_first = models.BooleanField(default=False)
    published_at = models.DateTimeField("veröffentlicht am", null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "Text der Webseite"
        verbose_name_plural = "Texte der Webseite"
        ordering = ["kind", "menu_position", "title", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["website", "slug"],
                condition=models.Q(kind="page"),
                name="webseite_textseite_adresse",
            ),
            models.UniqueConstraint(
                fields=["website"],
                condition=models.Q(kind="greeting"),
                name="webseite_eine_begruessung",
            ),
            models.UniqueConstraint(
                fields=["website", "department"],
                condition=models.Q(kind="unit"),
                name="webseite_ein_text_je_einheit",
            ),
        ]

    def __str__(self) -> str:
        return self.title or self.get_kind_display()

    def save(self, *args, **kwargs):
        if self.kind == self.Kind.PAGE:
            from core.reorder import append_if_new

            append_if_new(
                self,
                "menu_position",
                WebsiteText.objects.filter(website_id=self.website_id, kind=self.Kind.PAGE),
            )
        super().save(*args, **kwargs)

    @property
    def is_published(self) -> bool:
        return self.published_at is not None

    @property
    def has_changes(self) -> bool:
        """Entwurf weicht von der veröffentlichten Fassung ab."""
        return (
            not self.is_published
            or self.title != self.published_title
            or self.body != self.published_body
            or self.image_id != self.published_image_id
            or (self.gallery or []) != (self.published_gallery or [])
            or self.gallery_interval != self.published_gallery_interval
            or self.gallery_random != self.published_gallery_random
            or self.show_captions != self.published_show_captions
            or (self.timeline or []) != (self.published_timeline or [])
            or self.timeline_newest_first != self.published_timeline_newest_first
        )

    def clean(self):
        import re

        if self.kind == self.Kind.PAGE:
            if not self.title.strip():
                raise ValidationError({"title": "Bitte einen Titel angeben."})
            if not re.match(SLUG_RE, self.slug or ""):
                raise ValidationError(
                    {"slug": "Nur Kleinbuchstaben, Ziffern und Bindestriche, z. B. „geschichte“."}
                )
            if self.slug in RESERVED_SLUGS:
                raise ValidationError({"slug": "Diese Adresse ist für die Webseite reserviert."})


class WebsiteRevision(models.Model):
    """Veröffentlichte Fassung eines Textes (Verlauf)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    text = models.ForeignKey(WebsiteText, on_delete=models.CASCADE, related_name="revisions")
    title = models.CharField(max_length=MAX_TITLE, blank=True)
    body = models.TextField(blank=True)
    image = models.ForeignKey(
        "website.WebsiteImage", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    gallery = models.JSONField(default=list, blank=True)
    gallery_interval = models.PositiveSmallIntegerField(default=GALLERY_INTERVAL)
    gallery_random = models.BooleanField(default=False)
    show_captions = models.BooleanField(default=False)
    timeline = models.JSONField(default=list, blank=True)
    timeline_newest_first = models.BooleanField(default=False)
    published_at = models.DateTimeField(default=timezone.now)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "Fassung eines Textes der Webseite"
        verbose_name_plural = "Fassungen der Texte der Webseite"
        ordering = ["-published_at", "-pk"]

    def __str__(self) -> str:
        return f"Fassung vom {timezone.localtime(self.published_at):%d.%m.%Y %H:%M}"


def image_path(instance, filename: str) -> str:
    return f"website/{instance.organization_id}/{instance.key}-{filename}"


class WebsiteImage(models.Model):
    """Bild für die Webseite, beim Hochladen verkleinert und ohne Metadaten."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    website = models.ForeignKey(Website, on_delete=models.CASCADE, related_name="images")
    # Öffentliche Kennung im Text (Markdown ``![Alt](bild:<key>)``) und in Adressen
    key = models.CharField(max_length=24, unique=True)
    file = PrivateFileField("Bild", storage=private_storage, upload_to=image_path)
    small = PrivateFileField("Bild klein", storage=private_storage, upload_to=image_path)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    caption = models.CharField("Bildunterschrift", max_length=300, blank=True)
    alt_text = models.CharField("Alternativtext", max_length=300, blank=True)
    # Bewusst ohne Beschreibung (reiner Schmuck): dann alt="" auf der Webseite,
    # sonst ersetzt die Bildunterschrift einen fehlenden Alternativtext
    decorative = models.BooleanField("nur Schmuck", default=False)
    # Original (höchstens 4000 px, ohne Metadaten) und gewählter Ausschnitt: Damit lässt
    # sich der Ausschnitt später neu wählen, ohne dass etwas verloren geht (Ralf 01.11.).
    # Ältere Bilder haben kein Original; dann gilt ``file`` als Original.
    original = PrivateFileField(
        "Original", storage=private_storage, upload_to=image_path, blank=True
    )
    # {"x", "y", "width", "height"} in Prozent des (gedrehten) Originals, "rotation",
    # "aspect" (Schlüssel des Formats); leer = ganzes Bild
    crop = models.JSONField("Ausschnitt", default=dict, blank=True)
    # Optional: gehört zu einer Untereinheit (nur Filter für die Auswahl, keine Sperre)
    department = models.ForeignKey(
        "organizations.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="gehört zu",
    )
    # Steigt mit jedem neuen Ausschnitt oder Ersetzen: neue Adresse für Zwischenspeicher
    version = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Zum Sortieren der Galerie (Ralf 05.11.): Aufnahmezeit aus der Kamera und Dateiname,
    # beim Hochladen gemerkt; die Bilddatei selbst bleibt ohne Metadaten
    taken_at = models.DateTimeField("aufgenommen", null=True, blank=True)
    file_name = models.CharField("Dateiname", max_length=200, blank=True)

    class Meta:
        verbose_name = "Bild der Webseite"
        verbose_name_plural = "Bilder der Webseite"
        ordering = ["-uploaded_at", "-pk"]

    def __str__(self) -> str:
        return self.caption or self.alt_text or f"Bild {self.key}"

    @staticmethod
    def new_key() -> str:
        return secrets.token_urlsafe(12)

    @property
    def public_key(self) -> str:
        """Kennung in öffentlichen Adressen, mit Fassung (``<key>-v3``), damit nach
        neuem Ausschnitt kein Zwischenspeicher das alte Bild zeigt."""
        return f"{self.key}-v{self.version}" if self.version else self.key


# Galerie (Ralf 05.11.2026): Alben mit Bildern, höchstens zwei Ebenen (Album › Unteralbum),
# für alle Vereine. Die Bilder kommen aus der Bilderverwaltung (WebsiteImage).
MAX_ALBUM_TITLE = 120
MAX_ALBUM_TEXT = 2000
MAX_ALBUM_IMAGES = 1000

# Sortierung (Ralf 05.11.): Bilder je Album, Alben je Ebene; „manual“ = eigene Reihenfolge
IMAGE_ORDERS = {
    "manual": gettext_lazy("eigene Reihenfolge"),
    "taken": gettext_lazy("Aufnahmedatum, älteste zuerst"),
    "taken_desc": gettext_lazy("Aufnahmedatum, neueste zuerst"),
    "name": gettext_lazy("Dateiname A–Z"),
    "name_desc": gettext_lazy("Dateiname Z–A"),
    "uploaded": gettext_lazy("Hochladedatum, älteste zuerst"),
    "uploaded_desc": gettext_lazy("Hochladedatum, neueste zuerst"),
    "caption": gettext_lazy("Bildunterschrift A–Z"),
    "caption_desc": gettext_lazy("Bildunterschrift Z–A"),
}
ALBUM_ORDERS = {
    "manual": gettext_lazy("eigene Reihenfolge"),
    "date_desc": gettext_lazy("Datum, neueste zuerst"),
    "date": gettext_lazy("Datum, älteste zuerst"),
    "title": gettext_lazy("Titel A–Z"),
    "title_desc": gettext_lazy("Titel Z–A"),
}
DEFAULT_IMAGE_ORDER = "taken"
DEFAULT_ALBUM_ORDER = "date_desc"


class GalleryAlbum(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    website = models.ForeignKey(Website, on_delete=models.CASCADE, related_name="albums")
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="gehört zu Album",
    )
    title = models.CharField("Titel", max_length=MAX_ALBUM_TITLE)
    slug = models.CharField("Adresse", max_length=60)
    description = models.TextField("Beschreibung", max_length=MAX_ALBUM_TEXT, blank=True)
    # Datum des Anlasses (optional); die Webseite zeigt das Jahr
    date = models.DateField("Datum", null=True, blank=True)
    cover = models.ForeignKey(
        "website.WebsiteImage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Titelbild",
    )
    position = models.PositiveIntegerField("Reihenfolge", default=0)
    published = models.BooleanField("auf der Webseite zeigen", default=False)
    show_captions = models.BooleanField("Bildunterschriften zeigen", default=True)
    image_order = models.CharField(
        "Bilder sortieren nach",
        max_length=20,
        choices=list(IMAGE_ORDERS.items()),
        default=DEFAULT_IMAGE_ORDER,
    )
    children_order = models.CharField(
        "Unteralben sortieren nach",
        max_length=20,
        choices=list(ALBUM_ORDERS.items()),
        default=DEFAULT_ALBUM_ORDER,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "Album"
        verbose_name_plural = "Alben"
        ordering = ["position", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["website", "slug"], name="galerie_album_adresse"),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        from core.reorder import append_if_new

        append_if_new(
            self,
            "position",
            GalleryAlbum.objects.filter(website_id=self.website_id, parent_id=self.parent_id),
        )
        super().save(*args, **kwargs)

    def clean(self):
        import re

        if not (self.title or "").strip():
            raise ValidationError({"title": gettext("Bitte einen Titel angeben.")})
        if not re.match(SLUG_RE, self.slug or ""):
            raise ValidationError(
                {
                    "slug": gettext(
                        "Nur Kleinbuchstaben, Ziffern und Bindestriche, z. B. „schuetzenfest-2024“."
                    )
                }
            )
        if self.parent_id:
            if self.parent_id == self.pk:
                raise ValidationError(
                    {"parent": gettext("Ein Album kann nicht in sich selbst liegen.")}
                )
            if self.parent.website_id != self.website_id:
                raise ValidationError({"parent": gettext("Unbekanntes Album.")})
            if self.parent.parent_id:
                raise ValidationError({"parent": gettext("Alben haben höchstens zwei Ebenen.")})
            if self.pk and GalleryAlbum.objects.filter(parent_id=self.pk).exists():
                raise ValidationError(
                    {
                        "parent": gettext(
                            "Ein Album mit Unteralben kann nicht selbst Unteralbum werden."
                        )
                    }
                )


class GalleryItem(models.Model):
    """Bild in einem Album, in der gewählten Reihenfolge."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    album = models.ForeignKey(GalleryAlbum, on_delete=models.CASCADE, related_name="items")
    image = models.ForeignKey(
        "website.WebsiteImage", on_delete=models.CASCADE, related_name="gallery_items"
    )
    position = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Bild im Album"
        verbose_name_plural = "Bilder im Album"
        ordering = ["position", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["album", "image"], name="galerie_bild_einmal"),
        ]

    def __str__(self) -> str:
        return f"{self.album} · {self.image}"
