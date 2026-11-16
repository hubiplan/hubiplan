"""Lesbare Adressen auf der Webseite (Webseite #149).

Würden, Reihen und Wettbewerbe hatten auf der Webseite Adressen mit einer internen Kennung
(``/majestaeten/9565d7931db76805ced9/``). Jetzt bekommen sie eine lesbare Adresse aus dem Namen
(Kleinbuchstaben, Umlaute umschrieben, Bindestriche), eindeutig je Einheit. Wer sie in HUBIplan
selbst festlegt, behält sie; sonst folgt sie dem Namen. Frühere Adressen bleiben in
``web_slug_history``, damit die Webseite sie dauerhaft weiterleitet (301).
"""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext as _

MAX_LEN = 60
MAX_HISTORY = 20
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# Adressen, die die Webseite selbst belegt (Unterseiten unter derselben Adresse)
RESERVED = frozenset({"reihe", "tabelle", "stand"})


def make_slug(text: str, fallback: str) -> str:
    """Lesbare Adresse aus einem Namen: „Hubertuskönige“ → „hubertuskoenige“."""
    base = (text or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        base = base.replace(a, b)
    slug = slugify(base)[:MAX_LEN].strip("-")
    return slug or fallback


def clean_manual(value: str) -> str:
    """Eingabe für eine selbst festgelegte Adresse; wirft ValidationError."""
    slug = make_slug(value, "")
    if not slug or slug.isdigit() or slug in RESERVED or re.fullmatch(r"[a-f0-9]{20}", slug):
        raise ValidationError(_("Bitte eine Adresse aus Buchstaben und Ziffern angeben."))
    return slug


WEB_SLUG_OWN_FIELDS = ("web_slug", "web_slug_auto", "web_slug_history")


class WebSlugMixin(models.Model):
    """Felder und Pflege der lesbaren Adresse; Unterklassen nennen Quelle und Geschwister."""

    # db_default: Die vorige Fassung legt weiter Zeilen ohne diese Spalten an (docs/releases.md)
    web_slug = models.CharField(
        "Adresse auf der Webseite", max_length=MAX_LEN, blank=True, default="", db_default=""
    )
    # True: folgt dem Namen; False: in HUBIplan selbst festgelegt
    web_slug_auto = models.BooleanField("Adresse aus dem Namen", default=True, db_default=True)
    web_slug_history = models.JSONField("frühere Adressen", default=list, db_default=[], blank=True)

    WEB_SLUG_FALLBACK = "seite"
    # Felder, aus denen die Adresse entsteht; ein Speichern nur anderer Felder lässt sie
    WEB_SLUG_FIELDS = frozenset(
        {"name", "name_plural", "title", "date", "web_slug", "web_slug_auto"}
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if update_fields is None:
            self.refresh_web_slug()
        elif set(update_fields) & self.WEB_SLUG_FIELDS:
            self.refresh_web_slug()
            kwargs["update_fields"] = {*update_fields, *WEB_SLUG_OWN_FIELDS}
        super().save(*args, **kwargs)

    def web_slug_source(self) -> str:  # pragma: no cover – in den Unterklassen
        raise NotImplementedError

    def web_slug_siblings(self):  # pragma: no cover – in den Unterklassen
        raise NotImplementedError

    def set_web_slug(self, value: str | None) -> None:
        """Aus der Oberfläche: leer = wieder aus dem Namen, sonst selbst festgelegt."""
        if value is None or not str(value).strip():
            self.web_slug_auto = True
        else:
            self.web_slug_auto = False
            self.web_slug = clean_manual(str(value))

    def refresh_web_slug(self) -> None:
        old = self.web_slug
        if self.web_slug_auto or not self.web_slug:
            base = make_slug(self.web_slug_source(), self.WEB_SLUG_FALLBACK)
        else:
            base = self.web_slug
        # Unverändert (auch mit Zusatz „-2“): keine Abfrage bei jedem Speichern
        if old and self.pk and (old == base or re.fullmatch(re.escape(base) + r"-\d+", old)):
            return
        taken = set(self.web_slug_siblings().exclude(pk=self.pk).values_list("web_slug", flat=True))
        slug, n = base, 2
        while slug in taken or slug in RESERVED:
            suffix = f"-{n}"
            slug, n = f"{base[: MAX_LEN - len(suffix)]}{suffix}", n + 1
        self.web_slug = slug
        if old and old != slug:
            history = [s for s in (self.web_slug_history or []) if s not in (old, slug)]
            self.web_slug_history = [old, *history][:MAX_HISTORY]
        elif slug in (self.web_slug_history or []):
            self.web_slug_history = [s for s in self.web_slug_history if s != slug]


def backfill(rows, source, fallback: str) -> None:
    """Für Migrationen: vorhandenen Einträgen eine Adresse geben, eindeutig je Einheit, in der
    Reihenfolge der Anlage (ältere behalten die Adresse ohne Zusatz)."""
    taken: dict[int, set[str]] = {}
    for row in rows.order_by("organization_id", "pk"):
        used = taken.setdefault(row.organization_id, set())
        base = make_slug(source(row), fallback)
        slug, n = base, 2
        while slug in used or slug in RESERVED:
            suffix = f"-{n}"
            slug, n = f"{base[: MAX_LEN - len(suffix)]}{suffix}", n + 1
        used.add(slug)
        row.web_slug = slug
        row.save(update_fields=["web_slug"])


def take_from_attrs(attrs: dict, instance, siblings) -> None:
    """Für Serializer: ``web_slug`` aus der Oberfläche prüfen und ``web_slug_auto`` setzen.
    Leer heißt „aus dem Namen“. Eine selbst gewählte Adresse muss frei sein."""
    from rest_framework import serializers

    if "web_slug" not in attrs:
        return
    given = str(attrs.pop("web_slug") or "").strip()
    if not given:
        attrs["web_slug_auto"] = True
        return
    try:
        slug = clean_manual(given)
    except ValidationError as exc:
        raise serializers.ValidationError({"web_slug": exc.messages}) from exc
    others = siblings.exclude(pk=instance.pk) if instance is not None else siblings
    if others.filter(web_slug=slug).exists():
        raise serializers.ValidationError(
            {"web_slug": _("Diese Adresse ist schon vergeben: {slug}").format(slug=slug)}
        )
    attrs["web_slug"] = slug
    attrs["web_slug_auto"] = False
