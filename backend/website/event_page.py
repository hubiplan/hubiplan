"""Veranstaltungsseite (Anmeldung A4, Konzept 3.8a): eine Textseite der Webseite zu einem
öffentlichen Termin.

Titel, Text und eigene Abschnitte pflegt der Verein wie bei jeder Textseite (Entwurf,
Veröffentlichen, Menüverwaltung, KI-Schnittstelle). Eckdaten, Programm, Preise, freie Plätze
und der Knopf zur Anmeldung kommen aus dem Termin, nichts wird doppelt gepflegt. Der
Menüpunkt verschwindet am Tag nach dem Ende; die Seite bleibt als Rückblick erreichbar oder
wird mit ``hide_after_event`` ausgeblendet. Teilnehmende stehen nie auf der Seite.
"""

from __future__ import annotations

import datetime

from django.utils import timezone

from core.webslug import make_slug

from .content_models import RESERVED_SLUGS, WebsiteText
from .models import Website


def last_day(event) -> datetime.date:
    end = event.ends_at or event.starts_at
    return timezone.localtime(end).date() if end else datetime.date.max


def ended(event, today: datetime.date | None = None) -> bool:
    """Ist die Veranstaltung vorbei (ab dem Tag nach dem letzten Tag)?"""
    return (today or timezone.localdate()) > last_day(event)


def shown(event, website: Website) -> bool:
    """Darf die Seite Angaben dieses Termins zeigen? Nur öffentliche eigene Termine."""
    from events.models import Event

    from .services import data_area

    return (
        event is not None
        and event.visibility == Event.Visibility.PUBLIC
        and not event.source_stale
        and event.organization_id == data_area(website.organization).pk
    )


def in_menu(text: WebsiteText, today: datetime.date | None = None) -> bool:
    """Menüpunkt einer Textseite: bei Veranstaltungsseiten nur bis zum Ende."""
    return text.event_id is None or not ended(text.event, today)


def hidden(text: WebsiteText, today: datetime.date | None = None) -> bool:
    """Seite nach dem Ende ausgeblendet (wählbar)."""
    return text.event_id is not None and text.hide_after_event and ended(text.event, today)


def page_for(event, website: Website) -> WebsiteText | None:
    return (
        WebsiteText.objects.filter(website=website, kind=WebsiteText.Kind.PAGE, event=event)
        .order_by("pk")
        .first()
    )


def _free_slug(website: Website, title: str) -> str:
    base = make_slug(title, "veranstaltung")[:50].strip("-") or "veranstaltung"
    taken = set(
        WebsiteText.objects.filter(website=website, kind=WebsiteText.Kind.PAGE).values_list(
            "slug", flat=True
        )
    )
    slug, n = base, 2
    while slug in taken or slug in RESERVED_SLUGS:
        slug, n = f"{base}-{n}", n + 1
    return slug


def create(event, website: Website, user=None) -> tuple[WebsiteText, bool]:
    """Veranstaltungsseite anlegen (als Entwurf) oder die vorhandene liefern."""
    existing = page_for(event, website)
    if existing is not None:
        return existing, False
    title = (event.title or "")[:120] or "Veranstaltung"
    text = WebsiteText(
        organization=website.organization,
        website=website,
        kind=WebsiteText.Kind.PAGE,
        slug=_free_slug(website, title),
        title=title,
        body="",
        event=event,
        updated_by=user,
    )
    text.save()
    return text, True


def public_data(site, event) -> dict | None:
    """Eckdaten für die Webseite; None, wenn der Termin dort nicht (mehr) stehen darf."""
    from django.utils.translation import override

    from .public_views import _event_attachments, _event_registration

    if not shown(event, site.site):
        return None
    with override(site.site.language or "de"):
        registration = _event_registration(event, full=True)
    return {
        "title": event.title,
        "starts_at": event.starts_at,
        "ends_at": event.ends_at,
        "all_day": event.all_day,
        "hide_end_time": event.hide_end_time,
        "is_cancelled": event.is_cancelled,
        "location": event.location,
        "address": event.address,
        "directions": event.directions,
        "description": event.description,
        "programme": event.programme,
        "attachments": _event_attachments(site, event),
        "registration": registration,
        "ended": ended(event, site.today),
    }


def slugs(site) -> dict[int, str]:
    """Termin → Adresse seiner veröffentlichten Veranstaltungsseite (je Aufruf einmal)."""
    cached = getattr(site, "_event_page_slugs", None)
    if cached is None:
        cached = {}
        for t in (
            site.published_texts()
            .filter(kind=WebsiteText.Kind.PAGE, event__isnull=False)
            .select_related("event")
            .order_by("pk")
        ):
            if not hidden(t, site.today) and shown(t.event, site.site):
                cached.setdefault(t.event_id, t.slug)
        site._event_page_slugs = cached
    return cached
