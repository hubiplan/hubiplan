"""Daten für die Einstellungen der Webseite: Domains, Links, Kopfbild, Auswahl der Abschnitte."""

from __future__ import annotations

import datetime

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext

from organizations.theme import effective_theme

from . import home, menu, services
from .models import (
    BLOCKS,
    HEADER_IMAGE_FIELDS,
    PreviewLink,
    Website,
    WebsiteDomain,
    WebsiteImage,
    blocks_without_module,
    header_ids,
    header_value,
)

MENU_ITEM_FIELDS = (
    "label",
    "default_label",
    "renamable",
    "hint",
    "toggle",
    "heading",
    "parent",
    "url",
)


def header_image_id(website: Website, key: str = "header_image") -> int | list[int] | None:
    """Kopfbild (``header_image``) oder Kopfbild für schmale Bildschirme (Webseite #73): null,
    eine Bildnummer oder ab zwei Bildern eine Liste (#480)."""
    flag = HEADER_IMAGE_FIELDS[key]
    return header_value(
        WebsiteImage.objects.filter(website=website, **{flag: True}).values_list("pk", flat=True)
    )


def set_header_image(website: Website, value, key: str = "header_image") -> None:
    """Kopfbild(er) setzen: null, eine Bildnummer oder eine Liste (#480)."""
    flag = HEADER_IMAGE_FIELDS[key]
    ids = header_ids(value)
    WebsiteImage.objects.filter(website=website, **{flag: True}).exclude(pk__in=ids).update(
        **{flag: False}
    )
    if ids:
        WebsiteImage.objects.filter(website=website, pk__in=ids).update(**{flag: True})


def can_import_designs(user) -> bool:
    from access.permissions import is_platform_admin
    from accounts.mfa_policy import has_mfa

    # Superuser nur mit Zwei-Faktor-Anmeldung, wie die Plattform-Verwaltung (AUTH-04)
    if not (user and user.is_authenticated):
        return False
    return bool((user.is_superuser and has_mfa(user)) or is_platform_admin(user))


def domain_data(d: WebsiteDomain) -> dict:
    return {"id": d.pk, "hostname": d.hostname, "is_primary": d.is_primary}


def link_data(link: PreviewLink) -> dict:
    return {
        "id": link.pk,
        "label": link.label,
        "expires_at": link.expires_at,
        "revoked_at": link.revoked_at,
        "is_active": link.is_active,
        "created_at": link.created_at,
        "created_by": (link.created_by.get_full_name() or link.created_by.email)
        if link.created_by
        else "",
    }


def site_url(website: Website) -> str | None:
    # Testserver: alle Webseiten laufen unter einer festen Adresse (z. B. …/vereinsseite/)
    if settings.WEBSITE_PUBLIC_URL:
        return settings.WEBSITE_PUBLIC_URL.rstrip("/") + "/"
    primary = next(iter(website.domains.all()), None)
    return f"https://{primary.hostname}/" if primary else None


def home_choices(website: Website) -> dict:
    """Auswahl für die eigenen Abschnitte der Startseite: Rollen auf der Webseite, Alben
    der Galerie und kommende öffentliche Termine (je einmal, nach Datum)."""
    from events.models import Event, EventCategory
    from events.recurrence import occurrences
    from places.models import Place

    from .content_models import GalleryAlbum, WebsiteDocument
    from .public import SiteView

    site = SiteView(website)
    now = timezone.now()
    found = occurrences(
        Event.objects.filter(
            organization=site.area, visibility=Event.Visibility.PUBLIC, source_stale=False
        ),
        now,
        now + datetime.timedelta(days=home.EVENT_DAYS_AHEAD),
    )
    events, seen = [], set()
    for o in sorted(found, key=lambda o: o.starts_at):
        if o.event.pk not in seen and len(events) < 100:
            seen.add(o.event.pk)
            # external: aus einem abonnierten fremden Kalender (Gesamtaudit 15.11., MCP-03)
            events.append(
                {
                    "id": o.event.pk,
                    "title": o.event.title,
                    "starts_at": o.starts_at,
                    "external": o.event.external_source_id is not None,
                }
            )
    return {
        "roles": [{"id": r.pk, "name": r.name} for r in site.own_roles().filter(on_website=True)],
        "albums": [
            {"id": a.pk, "title": a.title}
            for a in GalleryAlbum.objects.filter(website=website).order_by("title", "pk")
        ],
        "events": events,
        # Weitere Abschnittsarten: Orte (Anfahrt), Terminkategorien, Dokumente
        "places": [
            {"id": p.pk, "name": p.full_name}
            for p in sorted(
                Place.objects.filter(organization=site.area, is_active=True)
                .exclude(parent__is_active=False)
                .select_related("parent"),
                key=lambda p: p.full_name.lower(),
            )
        ],
        "categories": [
            {"id": c.pk, "name": c.name}
            for c in EventCategory.objects.filter(organization=site.area, is_active=True).order_by(
                "name"
            )
        ],
        "documents": [
            {"id": d.pk, "title": d.title}
            for d in WebsiteDocument.objects.filter(website=website, published=True)
        ],
        # Majestäten einer Untereinheit, Ergebnisse eines Wettbewerbs (14.11.2026)
        "units": [{"id": u.pk, "name": u.name} for u in site.units],
        "competitions": [
            {"id": c.pk, "title": c.title, "date": c.date}
            for c in home.competition_choices(site).order_by("-date", "-pk")[:100]
        ],
        "live_facts": dict(home.LIVE_FACTS),
    }


def page_section_options(org, website: Website) -> dict:
    """Auswahl für die Abschnitte der Textseiten (G4): dieselben Arten wie auf der Startseite,
    dazu „body“ (Bild und Text der Seite) als fester Abschnitt."""
    hide = blocks_without_module(org)
    theme = effective_theme(org.ancestors())
    return {
        "block_labels": {
            **{k: v for k, v in BLOCKS.items() if k not in hide},
            "units": org.department_label_plural or BLOCKS["units"],
        },
        "blocks": {k: website.block_on(k) for k in BLOCKS},
        "home_labels": {"body": gettext("Text der Seite")},
        "home_hints": {"body": gettext("Bild und Text aus dem Feld oben")},
        "home_needs_block": {},
        # Textseiten haben zusätzlich das Titelbild (G6)
        "home_kinds": home.ALL_KINDS,
        "home_kind_hints": {**home.KIND_HINTS, **home.PAGE_KIND_HINTS},
        "home_kind_needs_block": home.KIND_NEEDS_BLOCK,
        "home_choices": home_choices(website),
        "palette": theme["palette"],
        "gradients": theme["gradients"],
        "units": [
            {"id": u.pk, "name": u.name} for u in services.in_tree_order(services.units_below(org))
        ],
        "menu_items": [
            {"key": key, **{f: item.get(f) for f in MENU_ITEM_FIELDS}}
            for key, item in menu.items(website).items()
        ],
    }


def unit_section_options(org, website: Website) -> dict:
    """Auswahl für die Abschnitte der Seiten der Untereinheiten (#491): dieselben Arten wie auf
    Textseiten (ohne Titelbild), dazu die festen Blöcke der Untereinheit."""
    from .home import KIND_HINTS, KINDS

    options = page_section_options(org, website)
    options["home_labels"] = {
        "body": gettext("Text der Seite"),
        "contact": gettext("Kontakt"),
        "homepage": gettext("Eigene Homepage"),
        "honors": gettext("Würdenträger"),
        "events": gettext("Nächste Termine"),
        "news": gettext("Aktuelles (Beiträge)"),
        "follow": gettext("Folgt uns"),
    }
    options["home_hints"] = {
        "body": gettext("Bild, Text und Bilderkarussell aus den Feldern oben"),
        "contact": gettext("Ansprechpartner der Untereinheit"),
        "homepage": gettext("Link zur eigenen Homepage, wenn freigegeben"),
        "honors": gettext("aktuelle Majestäten der Untereinheit"),
        "events": gettext("die nächsten Termine der Untereinheit"),
        "news": gettext("neueste eigene Beiträge und die aus Instagram und Facebook"),
        "follow": gettext("Links zu den sozialen Medien der Untereinheit"),
    }
    options["home_needs_block"] = {
        "contact": "board",
        "honors": "honors",
        "events": "events",
        "news": "posts",
        "follow": "social",
    }
    options["home_kinds"] = KINDS
    options["home_kind_hints"] = KIND_HINTS
    return options


# --- zurückgehaltene Nachrichten aus dem Kontaktformular ---


def held_data(m) -> dict:
    return {
        "id": m.pk,
        "recipient_name": m.recipient_name,
        "sender_name": m.sender_name,
        "sender_email": m.sender_email,
        "subject": m.subject,
        "body": m.body,
        "reason": m.reason,
        "created_at": m.created_at,
    }
