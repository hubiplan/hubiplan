"""Ausgabedaten der Termine: Zeilen der Schnittstelle für Termine, Rückmeldungen und Feeds."""

from __future__ import annotations

from django.db import transaction
from django.urls import reverse
from django.utils.translation import gettext

from oidc import nc_talk

from . import (
    attachments,
    maps,
    rsvp,
    services,
)
from .models import (
    MAX_GUESTS,
    CalendarPublication,
    Event,
    EventAttachment,
    EventCategory,
    EventResponse,
    ExternalCalendar,
    PersonalCalendar,
)
from .recurrence import Occurrence
from .serializers import (
    exception_data,
)

# --- Darstellung ---


def category_data(cat: EventCategory | None) -> dict | None:
    if cat is None:
        return None
    return {"id": cat.pk, "name": cat.name, "color": cat.color}


def occurrence_data(
    occ: Occurrence,
    viewer: services.Viewer,
    mine: dict[int, str] | None = None,
    video: dict[int, dict] | None = None,
) -> dict:
    """``mine``: eigene Rückmeldungen (Mitgliederbereich), Termin → Zu-/Absage.
    ``video``: Videoräume (Talk) je Termin."""
    event = occ.event
    data = {
        "key": occ.key,
        "event_id": event.pk,
        "title": event.title,
        "starts_at": occ.starts_at,
        "ends_at": occ.ends_at,
        "original_start": occ.original_start,
        "all_day": event.all_day,
        "hide_end_time": event.hide_end_time,
        "location": event.location,
        "address": event.address,
        "category": category_data(event.category),
        "visibility": event.visibility,
        "is_cancelled": occ.is_cancelled,
        "note": occ.note,
        "is_moved": occ.is_moved,
        "is_series": event.is_series,
        "changed_at": event.changed_at,
        "owner": services.owner_label(event, short=True),
        "level": services.level(event),
        "department_id": event.department_id,
        # Fremder Kalender (Vereinsplaner, iCal), aus dem der Termin stammt
        "source": event.external_source.name if event.external_source_id else None,
        "own": viewer.owns(event),
        "can_edit": viewer.can_edit(event),
        "rsvp_enabled": event.rsvp_enabled,
        # App: Hinweis „Rückmeldung fehlt“ vor dem Anmeldeschluss
        "rsvp_deadline": event.rsvp_deadline if event.rsvp_enabled else None,
        # Videoraum (Nextcloud Talk): Link und Passwort
        "video": (video or {}).get(event.pk),
    }
    if viewer.kind == "member":
        data["my_response"] = (mine or {}).get(event.pk) if event.rsvp_enabled else None
    return data


def rsvp_data(event: Event, viewer: services.Viewer) -> dict:
    """Stand der Zu- und Absagen für die Detailansicht."""
    data = {
        "enabled": event.rsvp_enabled,
        "deadline": event.rsvp_deadline,
        "capacity": event.rsvp_capacity,
        "guests_allowed": event.rsvp_guests,
        "max_guests": MAX_GUESTS,
        "maybe_allowed": event.rsvp_maybe,
        "note_allowed": event.rsvp_note,
        "note_question": event.rsvp_note_question if event.rsvp_note else "",
    }
    if not event.rsvp_enabled and not event.responses.exists():
        return data
    s = rsvp.summary(event)
    if event.rsvp_capacity:
        data["free"] = max(0, event.rsvp_capacity - s.persons)
    if viewer.kind == "member":
        mine = event.responses.filter(membership_id=viewer.membership_id).first()
        data["mine"] = response_data(mine) if mine else None
        allowed, reason = rsvp.member_can_respond(event)
        if allowed and not rsvp.is_invited(event, viewer.membership_id):
            allowed, reason = False, "Zu diesem Termin sind Sie nicht eingeladen."
        data["can_respond"] = allowed
        data["reason"] = gettext(reason) if reason else ""
    scope = viewer.response_scope(event)
    if scope is not None:
        data["can_view_list"] = True
        data["can_enter"] = event.rsvp_enabled
        if scope == "all":
            data["summary"] = {
                "yes": s.yes,
                "no": s.no,
                "maybe": s.maybe,
                "guests": s.guests,
                "persons": s.persons,
            }
    return data


def registration_data(event: Event, viewer: services.Viewer) -> dict | None:
    """Verbindliche Anmeldung am Termin (Modul „Anmeldungen“), nur ein kurzer Stand;
    Einzelheiten unter ``<termin>/registration/``."""
    from registrations import services as reg

    if viewer.kind == "org" and event.organization_id != viewer.org.pk:
        return _club_registration_data(event, viewer)
    if not reg.module_on(viewer.org):
        return None
    setup = reg.setup_of(event)
    can_setup = (
        viewer.kind == "org"
        and viewer.owns(event)
        and viewer.can_edit(event)
        and "registrations.edit" in viewer.perms
    )
    if setup is None:
        return {"enabled": False, "can_setup": can_setup} if can_setup else None
    value = reg.state(setup)
    return {
        "enabled": True,
        "state": value,
        "state_text": reg.state_text(setup, value),
        "closes_at": setup.closes_at,
        "free": reg.free(setup),
        "can_setup": can_setup,
        "can_view_list": viewer.kind == "org"
        and viewer.owns(event)
        and "registrations.view" in viewer.perms,
        "can_register": viewer.kind == "member",
    }


def _club_registration_data(event: Event, viewer: services.Viewer) -> dict | None:
    """Termin des Dachverbands im Vereinskalender: Sammelanmeldung durch den Verein (A8)."""
    from core.tenancy import tenant_context
    from registrations import services as reg

    fed = services.federation_of(viewer.org)
    if (
        fed is None
        or event.organization_id != fed.pk
        or not reg.module_on(fed)
        or "registrations.edit" not in viewer.perms
        or "members.view" not in viewer.perms
    ):
        return None
    with tenant_context(fed.pk):
        setup = reg.setup_of(event)
        if setup is None or not setup.club_registration:
            return None
        value = reg.state(setup)
        return {
            "enabled": True,
            "state": value,
            "state_text": reg.state_text(setup, value),
            "closes_at": setup.closes_at,
            "free": reg.free(setup),
            "can_setup": False,
            "can_view_list": False,
            "can_register": False,
            "club_register": True,
        }


def response_data(r: EventResponse) -> dict:
    return {
        "status": r.status,
        "guests": r.guests,
        "note": r.note,
        "source": r.source,
        "updated_at": r.updated_at,
    }


def attachment_data(att: EventAttachment, base: str) -> dict:
    return attachments.data(att, f"{base}attachments/{att.pk}/")


def event_data(event: Event, viewer: services.Viewer, base: str) -> dict:
    can_edit = viewer.can_edit(event)
    data = {
        "id": event.pk,
        "version": event.version,
        "title": event.title,
        "description": event.description,
        "location": event.location,
        "address": event.address,
        "directions": event.directions,
        "programme": event.programme,
        "latitude": float(event.latitude) if event.latitude is not None else None,
        "longitude": float(event.longitude) if event.longitude is not None else None,
        "map_links": maps.for_event(event),
        "category": category_data(event.category),
        "all_day": event.all_day,
        "hide_end_time": event.hide_end_time,
        "starts_at": event.starts_at,
        "ends_at": event.ends_at,
        "visibility": event.visibility,
        "visibility_label": event.get_visibility_display(),
        "repeat": event.repeat,
        "repeat_label": event.get_repeat_display(),
        "repeat_interval": event.repeat_interval,
        "repeat_until": event.repeat_until,
        "is_cancelled": event.is_cancelled,
        "cancel_note": event.cancel_note,
        "changed_at": event.changed_at,
        "owner": services.owner_label(event),
        "level": services.level(event),
        "department_id": event.department_id,
        "can_edit": can_edit,
        "attachments": [
            attachment_data(a, f"{base}{event.pk}/") for a in attachments.shown(event, can_edit)
        ],
        "exceptions": [exception_data(e) for e in event.exceptions.all()],
        "rsvp": rsvp_data(event, viewer),
        "registration": registration_data(event, viewer),
        # Videolink aus einer Einladung oder von Hand (Talk-Räume von HUBIplan: T2)
        "video_url": event.video_url,
        "from_mail": bool(event.mail_uid),
        "source": (
            {
                "name": event.external_source.name,
                "kind": event.external_source.kind,
                "kind_label": event.external_source.get_kind_display(),
            }
            if event.external_source_id
            else None
        ),
        "can_hide": bool(
            event.external_source_id
            and viewer.kind == "org"
            and viewer.can_manage
            and viewer.owns(event)
        ),
        # Videoraum (Nextcloud Talk) mit Link und Passwort, sonst der fremde Videolink
        "video": nc_talk.video_of(event),
    }
    if can_edit and viewer.kind == "org" and not event.external_source_id:
        # Videoraum anlegen geht, wenn die Einheit Talk eingerichtet hat
        data["video_available"] = nc_talk.client_for(event.organization) is not None
    if can_edit:
        # Weitergabe: Angabe am Termin (leer = Voreinstellung) und die Voreinstellung
        owner = event.department if event.department_id else event.organization
        data["share_up"] = event.share_up
        data["share_down"] = event.share_down
        data["share_defaults"] = {
            "up": owner.events_share_up,
            "down": owner.events_share_down,
        }
    if viewer.finance and viewer.kind == "org" and viewer.owns(event):
        # Veranstaltungsfinanzen (Finanzen → Veranstaltungen), zu denen der Termin gehört
        project = event.project
        data["project"] = {"id": project.pk, "name": project.name} if project else None
        data["can_link_project"] = can_edit and viewer.finance == "edit"
    if viewer.kind == "org" and viewer.owns(event):
        data.update(related_data(event, viewer))
    if can_edit:
        data.update(circular_links(event, viewer))
        data["remind_days"] = event.remind_days
        data["reminded_at"] = event.reminded_at
        data["created_by"] = (
            event.created_by.get_full_name() or event.created_by.email if event.created_by else ""
        )
        data["created_at"] = event.created_at
    return data


def circular_links(event: Event, viewer: services.Viewer) -> dict:
    """Rundschreiben zu diesem Termin und ob man eines schreiben darf (Bearbeitende)."""
    from circulars.views import can_circulate

    if "circulars" not in (viewer.org.enabled_modules or []):
        return {}
    codes = {"dept.circulars.send"} if viewer.kind == "department" else {"circulars.send"}
    allowed = bool(codes & viewer.perms) and viewer.owns(event) and can_circulate(event)
    rows = event.circulars.filter(organization=viewer.org, department=viewer.department).order_by(
        "-created_at", "-pk"
    )
    return {
        "can_circular": allowed,
        "circulars": [
            {
                "id": c.pk,
                "subject": c.subject,
                "status": c.status,
                "status_label": c.get_status_display(),
                "sent_at": c.sent_at,
            }
            for c in rows[:20]
        ],
    }


def related_data(event: Event, viewer: services.Viewer) -> dict:
    """Was am Termin hängt: Versammlung, Dienstpläne, Belegungen (je nach Modul und Recht)."""
    modules = set(viewer.org.enabled_modules or [])
    perms = viewer.perms
    data: dict = {}
    if "meetings" in modules and "meetings.view" in perms:
        from meetings.models import Meeting

        meeting = Meeting.objects.filter(event=event).first()
        data["meeting"] = (
            {"id": meeting.pk, "status_label": meeting.get_status_display()} if meeting else None
        )
    if "helpers" in modules and "helpers.view" in perms:
        from helpers.models import HelperPlan

        plans = HelperPlan.objects.filter(
            organization=viewer.org, department__isnull=True, event=event
        ).order_by("pk")
        data["helper_plans"] = [
            {"id": p.pk, "title": p.title, "status_label": p.get_status_display()} for p in plans
        ]
        data["can_create_helper_plan"] = "helpers.edit" in perms
    if (
        "website" in modules
        and perms & {"website.content", "website.manage"}
        and viewer.kind == "org"
        and event.visibility == Event.Visibility.PUBLIC
    ):
        # Veranstaltungsseite (Anmeldung A4): Textseite der Webseite zu diesem Termin
        from website import event_page
        from website.services import website_of

        site = website_of(viewer.org)
        page = event_page.page_for(event, site) if site is not None else None
        if site is not None:
            data["web_page"] = (
                {"id": page.pk, "title": page.title, "is_published": page.is_published}
                if page
                else None
            )
    if "bookings" in modules and perms & {"bookings.view", "bookings.edit"}:
        rows = (
            event.bookings.filter(status__in=["requested", "confirmed"])
            .select_related("item")
            .order_by("starts_at", "pk")
        )
        data["bookings"] = [
            {"id": b.pk, "item": b.item.title, "status_label": b.get_status_display()} for b in rows
        ]
    return data


def mails(event: Event, kind: str) -> None:
    """E-Mails im Hintergrund verschicken, sobald der Termin gespeichert ist."""
    from .tasks import send_event_mails

    if rsvp.invited(event, sort=False).exists():
        transaction.on_commit(lambda: send_event_mails.delay(event.pk, kind))


def publication_data(request, pub: CalendarPublication | None) -> dict:
    if pub is None or not pub.is_public:
        return {"is_public": False, "ics_url": None, "json_url": None}
    key = pub.public_key
    return {
        "is_public": True,
        "ics_url": request.build_absolute_uri(reverse("public-calendar-ics", args=[key])),
        "json_url": request.build_absolute_uri(reverse("public-calendar", args=[key])),
    }


# --- Fremde Kalender (Vereinsplaner, iCal) ---


def external_data(cal: ExternalCalendar) -> dict:
    return {
        "id": cal.pk,
        "name": cal.name,
        "kind": cal.kind,
        "kind_label": cal.get_kind_display(),
        "has_token": bool(cal.token),
        "has_secret": bool(cal.secret),
        "category": category_data(cal.category),
        "visibility": cal.visibility,
        "share_down": cal.share_down,
        "is_active": cal.is_active,
        "last_sync_at": cal.last_sync_at,
        "last_successful_sync_at": cal.last_successful_sync_at,
        "last_error": cal.last_error,
        "event_count": cal.events.count(),
        "stale_hidden": cal.events.filter(source_stale=True).exists(),
        "hidden": [h for h in (cal.hidden or []) if isinstance(h, dict)],
    }


def feed_data(request, feed: PersonalCalendar | None, key: str = "") -> dict:
    """Den Link gibt es nur direkt nach dem Erstellen; gespeichert ist nur sein Hash."""
    active = feed is not None and feed.key_hash is not None
    return {
        "active": active,
        "ics_url": request.build_absolute_uri(reverse("personal-calendar-ics", args=[key]))
        if active and key
        else None,
    }


def board_feed_data(request, feed: PersonalCalendar | None, available: bool, key="") -> dict:
    active = available and feed is not None and feed.board_key_hash is not None
    return {
        "available": available,
        "active": active,
        "ics_url": request.build_absolute_uri(reverse("board-calendar-ics", args=[key]))
        if active and key
        else None,
    }
