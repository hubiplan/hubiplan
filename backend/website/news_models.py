"""Eigene Beiträge unter „Aktuelles“ (#707).

Neben den Beiträgen aus Instagram und Facebook schreibt der Verein hier selbst: Titel,
Datum (auch rückdatiert), Text in Markdown, Bilder und Videos. Wie bei den Textseiten gibt
es einen Entwurf und eine veröffentlichte Fassung; die Webseite zeigt nur die
veröffentlichte, die Vorschau den Entwurf. Videos erscheinen als Vorschaubild mit Link,
nie eingebettet (die Webseite lädt nichts von fremden Servern).
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext

from core.versioning import Versioned

from .content_models import MAX_TITLE, SLUG_RE

MAX_NEWS_BODY = 20_000
MAX_NEWS_IMAGES = 20
MAX_NEWS_VIDEOS = 6
MAX_VIDEO_TITLE = 120


class NewsPost(Versioned):
    # Fassung zählt nur hoch: nicht protokollieren, nicht zurückspielen (core/versioning.py)
    derived_fields = ("version",)

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    website = models.ForeignKey(
        "website.Website", on_delete=models.CASCADE, related_name="news_posts"
    )
    # Beitrag einer Untereinheit (erscheint auf ihrer Seite); leer = Beitrag der Einheit
    department = models.ForeignKey(
        "organizations.Department",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Untereinheit",
    )
    slug = models.CharField("Adresse", max_length=80)
    # Entwurf
    title = models.CharField("Titel", max_length=MAX_TITLE)
    date = models.DateField("Datum")
    body = models.TextField("Text", max_length=MAX_NEWS_BODY, blank=True)
    # Bilder unter dem Text: Nummern aus der Bilderverwaltung der Webseite, in Reihenfolge
    images = models.JSONField("Bilder", default=list, blank=True)
    # Videos als Link: [{"url", "title", "image"}] (image = Nummer eines Vorschaubilds)
    videos = models.JSONField("Videos", default=list, blank=True)
    # Veröffentlicht
    published_title = models.CharField(max_length=MAX_TITLE, blank=True)
    published_date = models.DateField(null=True, blank=True)
    published_body = models.TextField(blank=True)
    published_images = models.JSONField(default=list, blank=True)
    published_videos = models.JSONField(default=list, blank=True)
    published_at = models.DateTimeField("veröffentlicht am", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "Eigener Beitrag (Aktuelles)"
        verbose_name_plural = "Eigene Beiträge (Aktuelles)"
        ordering = ["-date", "-pk"]
        constraints = [
            models.UniqueConstraint(fields=["website", "slug"], name="webseite_beitrag_adresse"),
        ]

    def __str__(self) -> str:
        return self.title or gettext("Beitrag")

    @property
    def is_published(self) -> bool:
        return self.published_at is not None

    @property
    def has_changes(self) -> bool:
        return (
            not self.is_published
            or self.title != self.published_title
            or self.date != self.published_date
            or self.body != self.published_body
            or (self.images or []) != (self.published_images or [])
            or (self.videos or []) != (self.published_videos or [])
        )

    def clean(self):
        import re

        if not (self.title or "").strip():
            raise ValidationError({"title": gettext("Bitte einen Titel angeben.")})
        if not re.match(SLUG_RE, self.slug or ""):
            raise ValidationError(
                {
                    "slug": gettext(
                        "Nur Kleinbuchstaben, Ziffern und Bindestriche, z. B. „sommerfest-2019“."
                    )
                }
            )

    def publish(self, user=None) -> None:
        from django.utils import timezone

        self.published_title = self.title
        self.published_date = self.date
        self.published_body = self.body
        self.published_images = list(self.images or [])
        self.published_videos = [dict(v) for v in self.videos or []]
        self.published_at = timezone.now()
        self.updated_by = user
        self.save()

    def unpublish(self, user=None) -> None:
        self.published_at = None
        self.updated_by = user
        self.save()


def free_slug(website, title: str, exclude: int | None = None) -> str:
    """Adresse aus dem Titel, auf dieser Webseite noch frei (``sommerfest``, ``sommerfest-2``)."""
    from django.utils.text import slugify

    base = (
        slugify(
            (title or "")
            .replace("ä", "ae")
            .replace("ö", "oe")
            .replace("ü", "ue")
            .replace("Ä", "Ae")
            .replace("Ö", "Oe")
            .replace("Ü", "Ue")
            .replace("ß", "ss")
        )[:70].strip("-")
        or "beitrag"
    )
    taken = set(
        NewsPost.objects.filter(website=website, slug__startswith=base)
        .exclude(pk=exclude)
        .values_list("slug", flat=True)
    )
    slug, n = base, 2
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    return slug
