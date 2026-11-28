"""Entwurf der Webseite: Fassungen, Vorschau und Veröffentlichen (ohne HTTP)."""

from __future__ import annotations

from urllib.parse import quote

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework.exceptions import ValidationError

from audit.log import record

from . import home
from .models import (
    DESIGN_VERSIONS,
    DRAFT_FIELDS,
    HEADER_IMAGE_FIELDS,
    DesignVersion,
    Website,
    normalize_home_sections,
)
from .options import set_header_image, site_url
from .serializers import clean_draft, live_design


def version_data(version: DesignVersion) -> dict:
    return {
        "id": version.pk,
        "published_at": version.published_at,
        "published_by": (version.published_by.get_full_name() or version.published_by.email)
        if version.published_by
        else "",
    }


TEXT_VERSIONS = 10  # Fassungen › Texte und Textseiten: die zuletzt veröffentlichten


def text_versions(website: Website) -> list[dict]:
    """Zuletzt veröffentlichte Fassungen aller Texte (Begrüßung, Textseiten, Untereinheiten).

    Texte haben ihren eigenen Verlauf; ohne diese Liste sah es unter Webseite › Fassungen so
    aus, als gäbe es keine neueren Änderungen, wenn nur Texte veröffentlicht wurden."""
    from .content_models import WebsiteRevision

    rows = list(
        WebsiteRevision.objects.filter(text__website=website)
        .select_related("text", "published_by")
        .order_by("-published_at", "-pk")[:TEXT_VERSIONS]
    )
    # je Text höchstens MAX_REVISIONS Fassungen, also wenige Zeilen
    latest: dict[int, int] = {}
    for text_id, pk in (
        WebsiteRevision.objects.filter(text_id__in={r.text_id for r in rows})
        .order_by("-published_at", "-pk")
        .values_list("text_id", "pk")
    ):
        latest.setdefault(text_id, pk)
    return [
        {
            "id": r.pk,
            "text": r.text_id,
            "title": r.text.title or r.title or r.text.get_kind_display(),
            "kind": r.text.kind,
            "published_at": r.published_at,
            "published_by": (r.published_by.get_full_name() or r.published_by.email)
            if r.published_by
            else "",
            "current": latest.get(r.text_id) == r.pk,
        }
        for r in rows
    ]


def _apply_design(website: Website, values: dict) -> None:
    for key in DRAFT_FIELDS:
        if key in values and key not in HEADER_IMAGE_FIELDS:
            setattr(website, key, values[key])
    for key in HEADER_IMAGE_FIELDS:
        if key in values:
            set_header_image(website, values[key], key)


def publish_draft(website: Website, user, org) -> None:
    """Entwurf der Gestaltung veröffentlichen; die Fassung kommt in den Verlauf."""
    draft = clean_draft(website, website.draft)
    if not draft:
        raise ValidationError({"draft": [gettext("Es gibt keine Änderungen zum Veröffentlichen.")]})
    from .search import forget_index

    forget_index(website.pk)  # Startseite und Abschnitte neu durchsuchen (WEB-06)
    before = live_design(website)
    if not website.design_versions.exists():
        # Erste Veröffentlichung: der bisherige Stand bleibt zum Zurückholen
        DesignVersion.objects.create(
            organization=website.organization,
            website=website,
            data=before,
            published_at=website.updated_at or timezone.now(),
        )
    _apply_design(website, draft)
    website.draft = {}
    website.save()
    after = live_design(website)
    DesignVersion.objects.create(
        organization=website.organization, website=website, data=after, published_by=user
    )
    old = list(website.design_versions.values_list("pk", flat=True)[DESIGN_VERSIONS:])
    if old:
        DesignVersion.objects.filter(pk__in=old).delete()
    record(org, user, "update", website, {f"Gestaltung: {k}": [before[k], after[k]] for k in draft})


def content_only_draft(website: Website) -> bool:
    """Enthält der Entwurf nur Inhalte vorhandener Abschnitte der Startseite (F7)?"""
    draft = clean_draft(website, website.draft)
    if set(draft) != {"home_sections"}:
        return False
    live = normalize_home_sections(website.home_sections)
    return home.skeleton(draft["home_sections"]) == home.skeleton(live)


def preview_url(website: Website, token: str) -> str | None:
    base = site_url(website)
    if not base:
        return None
    url = f"{base}vorschau?schluessel={quote(token)}"
    if settings.WEBSITE_PUBLIC_URL:
        # Testserver: eine Adresse für alle Webseiten; der Link nennt, welche gemeint ist
        domain = website.domains.order_by("-is_primary", "pk").first()
        if domain:
            url += f"&seite={quote(domain.hostname)}"
    return url
