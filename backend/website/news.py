"""Eigene Beiträge unter „Aktuelles“ (#707): Prüfen, Anlegen, Ändern und die Daten für
Verwaltung, KI-Schnittstelle und Webseite."""

from __future__ import annotations

import datetime
import re

from django.utils.translation import gettext

from .content_models import MAX_TITLE, SLUG_RE, WebsiteImage
from .news_models import (
    MAX_NEWS_BODY,
    MAX_NEWS_IMAGES,
    MAX_NEWS_VIDEOS,
    MAX_VIDEO_TITLE,
    NewsPost,
    free_slug,
)

URL_MAX = 500
# Früheste Datum eines Beitrags (alte Vereinsbeiträge, z. B. aus WordPress)
MIN_DATE = datetime.date(1900, 1, 1)


class Invalid(ValueError):
    """Eingabe ungültig; ``field`` nennt das Feld (für Fehlermeldungen am Feld)."""

    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


def _image_ids(website, value, field: str, limit: int) -> list[int]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(
        isinstance(v, int) and not isinstance(v, bool) for v in value
    ):
        raise Invalid(field, gettext("Bitte eine Liste von Bildern angeben."))
    if len(value) > limit:
        raise Invalid(field, gettext("Höchstens {n} Bilder.").format(n=limit))
    if len(set(value)) != len(value):
        raise Invalid(field, gettext("Jedes Bild nur einmal."))
    known = set(
        WebsiteImage.objects.filter(website=website, pk__in=value).values_list("pk", flat=True)
    )
    if set(value) - known:
        raise Invalid(field, gettext("Unbekanntes Bild."))
    return list(value)


def clean_url(value, field: str = "videos") -> str:
    url = value.strip() if isinstance(value, str) else ""
    if len(url) > URL_MAX or not re.match(r"^https://[^\s/]+\.[^\s]+$", url):
        raise Invalid(field, gettext("Bitte die Adresse des Videos mit https:// angeben."))
    return url


def clean_videos(website, value) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        raise Invalid("videos", gettext("Bitte eine Liste von Videos angeben."))
    if len(value) > MAX_NEWS_VIDEOS:
        raise Invalid("videos", gettext("Höchstens {n} Videos.").format(n=MAX_NEWS_VIDEOS))
    images = [v.get("image") for v in value if v.get("image") is not None]
    known = set(_image_ids(website, list(dict.fromkeys(images)), "videos", 100))
    result = []
    for v in value:
        title = v.get("title") or ""
        if not isinstance(title, str) or len(title.strip()) > MAX_VIDEO_TITLE:
            raise Invalid(
                "videos",
                gettext("Titel des Videos: höchstens {n} Zeichen.").format(n=MAX_VIDEO_TITLE),
            )
        url = v.get("url")
        if not isinstance(url, str) or url.strip() in ("", "https://", "http://"):
            continue  # noch ohne Adresse (gerade in der Verwaltung hinzugefügt)
        image = v.get("image")
        result.append(
            {
                "url": clean_url(v.get("url")),
                "title": title.strip(),
                "image": image if image in known else None,
            }
        )
    return result


def clean_date(value) -> datetime.date:
    if isinstance(value, datetime.date):
        date = value
    else:
        try:
            date = datetime.date.fromisoformat(str(value or "").strip())
        except ValueError:
            raise Invalid("date", gettext("Bitte ein Datum angeben (JJJJ-MM-TT).")) from None
    if date < MIN_DATE or date > datetime.date.today() + datetime.timedelta(days=366):
        raise Invalid("date", gettext("Bitte ein Datum angeben (JJJJ-MM-TT)."))
    return date


def clean_department(website, value):
    if value in (None, ""):
        return None
    from . import services

    try:
        pk = int(value)
    except (TypeError, ValueError):
        raise Invalid("department", gettext("Unbekannte Untereinheit.")) from None
    unit = services.units_below(website.organization).filter(pk=pk).first()
    if unit is None:
        raise Invalid("department", gettext("Unbekannte Untereinheit."))
    return unit


EDITABLE = ("title", "date", "body", "images", "videos", "slug", "department")


def apply(post: NewsPost, data: dict) -> list[str]:
    """Felder aus ``data`` prüfen und in den Entwurf übernehmen; gibt die geänderten zurück."""
    website = post.website
    changed = []
    for field in EDITABLE:
        if field not in data:
            continue
        value = data[field]
        if field == "title":
            value = value.strip() if isinstance(value, str) else ""
            if not value:
                raise Invalid("title", gettext("Bitte einen Titel angeben."))
            if len(value) > MAX_TITLE:
                raise Invalid("title", gettext("Höchstens {n} Zeichen.").format(n=MAX_TITLE))
        elif field == "date":
            value = clean_date(value)
        elif field == "body":
            value = value if isinstance(value, str) else ""
            if len(value) > MAX_NEWS_BODY:
                raise Invalid("body", gettext("Höchstens {n} Zeichen.").format(n=MAX_NEWS_BODY))
        elif field == "images":
            value = _image_ids(website, value, "images", MAX_NEWS_IMAGES)
        elif field == "videos":
            value = clean_videos(website, value)
        elif field == "slug":
            value = (value or "").strip() if isinstance(value, str) else ""
            if not re.match(SLUG_RE, value) or len(value) > 80:
                raise Invalid(
                    "slug",
                    gettext(
                        "Nur Kleinbuchstaben, Ziffern und Bindestriche, z. B. „sommerfest-2019“."
                    ),
                )
            if NewsPost.objects.filter(website=website, slug=value).exclude(pk=post.pk).exists():
                raise Invalid("slug", gettext("Diese Adresse ist schon vergeben."))
        elif field == "department":
            value = clean_department(website, value)
            if (value.pk if value else None) != post.department_id:
                post.department = value
                changed.append(field)
            continue
        if getattr(post, field) != value:
            setattr(post, field, value)
            changed.append(field)
    return changed


def create(website, data: dict, user=None) -> NewsPost:
    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        raise Invalid("title", gettext("Bitte einen Titel angeben."))
    post = NewsPost(
        organization=website.organization,
        website=website,
        title="",
        date=datetime.date.today(),
        updated_by=user,
    )
    apply(post, {k: v for k, v in data.items() if k != "slug"})
    if data.get("slug"):
        apply(post, {"slug": data["slug"]})
    else:
        post.slug = free_slug(website, post.title)
    post.save()
    return post


def admin_data(post: NewsPost) -> dict:
    """Für die Verwaltung und die KI-Schnittstelle (Entwurf und Stand)."""
    return {
        "id": post.pk,
        "slug": post.slug,
        "title": post.title,
        "date": post.date.isoformat(),
        "body": post.body,
        "images": list(post.images or []),
        "videos": list(post.videos or []),
        "department": post.department_id,
        "department_name": post.department.name if post.department_id else None,
        "is_published": post.is_published,
        "has_changes": post.has_changes,
        "published_at": post.published_at,
        "updated_at": post.updated_at,
    }


def excerpt(text: str, words: int = 40) -> tuple[str, bool]:
    """Anriss für Listen: Markdown ohne Zeichen, höchstens ``words`` Wörter."""
    from .search import plain

    parts = plain(text or "").split()
    if len(parts) <= words:
        return " ".join(parts), False
    return " ".join(parts[:words]) + " …", True
