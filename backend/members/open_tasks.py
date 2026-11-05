"""Offene Aufgaben für die Startseite: Vorgänge, die eine Entscheidung brauchen.

Die Liste ist nur ein Einstieg; entschieden wird weiter in der jeweiligen
Fachansicht (Anfragen, Mitgliedsakte, Termin). Jede Art erscheint nur mit dem
Recht, das die Entscheidung erfordert.
"""

from __future__ import annotations

import datetime

from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext, ngettext
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from access.catalog import BILLING_VIEW, EVENTS_MANAGE, MEMBERS_EDIT, PHOTOS_MANAGE
from core.api_base import OrgScopedMixin
from organizations.models import Organization

LIMIT = 20
# Termine mit Zu-/Absagen, die bald stattfinden
EVENT_DAYS = 14


def _person(membership) -> str:
    p = membership.person
    return f"{p.first_name} {p.last_name}"


def member_tasks(org: Organization, perms: set[str]) -> list[dict]:
    from portal.models import ChangeRequest

    from .models import TransferRequest
    from .photo_models import MemberPhoto

    items: list[dict] = []
    if MEMBERS_EDIT in perms:
        for cr in ChangeRequest.objects.filter(
            organization=org, status=ChangeRequest.Status.PENDING
        ).select_related("membership__person")[:LIMIT]:
            items.append(
                {
                    "kind": "change_request",
                    "kind_label": gettext("Änderungsmeldung"),
                    "title": _person(cr.membership),
                    "detail": gettext("möchte eigene Daten ändern"),
                    "created_at": cr.created_at,
                    "link": "/mitglieder/anfragen/aenderungen",
                    "ref": cr.pk,
                    "membership": cr.membership_id,
                }
            )
        for tr in TransferRequest.objects.filter(
            from_org=org, status=TransferRequest.Status.PENDING
        ).select_related("person", "to_org")[:LIMIT]:
            items.append(
                {
                    "kind": "transfer",
                    "kind_label": gettext("Wechselanfrage"),
                    "title": f"{tr.person.first_name} {tr.person.last_name}",
                    "detail": gettext("{org} möchte aufnehmen").format(org=tr.to_org.display_name),
                    "created_at": tr.created_at,
                    "link": "/mitglieder/anfragen",
                }
            )
    if PHOTOS_MANAGE in perms:
        for photo in MemberPhoto.objects.filter(
            organization=org, status=MemberPhoto.Status.PENDING
        ).select_related("membership__person")[:LIMIT]:
            items.append(
                {
                    "kind": "photo",
                    "kind_label": gettext("Foto freigeben"),
                    "title": _person(photo.membership),
                    "detail": gettext("hat ein Foto hochgeladen"),
                    "created_at": photo.created_at,
                    "link": f"/mitglieder/{photo.membership_id}",
                    "ref": photo.pk,
                    "membership": photo.membership_id,
                }
            )
    return items


def event_tasks(org: Organization, perms: set[str]) -> list[dict]:
    from django.db.models import Count, Q

    from events.models import Event, EventResponse

    if EVENTS_MANAGE not in perms or "events" not in (org.enabled_modules or []):
        return []
    now = timezone.now()
    events = (
        Event.objects.filter(
            organization=org,
            department__isnull=True,
            rsvp_enabled=True,
            is_cancelled=False,
            starts_at__gte=now,
            starts_at__lte=now + datetime.timedelta(days=EVENT_DAYS),
        )
        .annotate(
            yes=Count("responses", filter=Q(responses__status=EventResponse.Status.YES)),
            no=Count("responses", filter=Q(responses__status=EventResponse.Status.NO)),
        )
        .order_by("starts_at")[:LIMIT]
    )
    local = timezone.localtime
    return [
        {
            "kind": "event",
            "kind_label": gettext("Rückmeldungen"),
            "title": e.title,
            "detail": gettext("am {date}: {yes} Zusagen, {no} Absagen").format(
                date=date_format(local(e.starts_at).date(), "SHORT_DATE_FORMAT", use_l10n=True),
                yes=e.yes,
                no=e.no,
            ),
            "created_at": e.starts_at,
            "link": f"/termine?termin={e.pk}&datum={local(e.starts_at):%Y-%m-%d}",
            "ref": e.pk,
        }
        for e in events
    ]


def billing_tasks(org: Organization, perms: set[str]) -> list[dict]:
    """Überfällige Rechnungen als ein Eintrag „Zu erledigen“ (UX-Audit 10.6)."""
    from billing.models import Invoice

    if BILLING_VIEW not in perms or "billing" not in (org.enabled_modules or []):
        return []
    overdue = Invoice.objects.filter(
        organization=org, status=Invoice.Status.OPEN, due_date__lt=timezone.localdate()
    )
    n = overdue.count()
    if not n:
        return []
    first = overdue.order_by("due_date").values_list("due_date", flat=True).first()
    return [
        {
            "kind": "invoices_overdue",
            "kind_label": gettext("Rechnungen"),
            "title": ngettext(
                "{n} Rechnung überfällig", "{n} Rechnungen überfällig", n
            ).format(n=n),
            "detail": gettext("älteste fällig seit {date}").format(
                date=date_format(first, "SHORT_DATE_FORMAT", use_l10n=True)
            ),
            "created_at": first,
            "link": "/finanzen/rechnungen?status=open&ueberfaellig=1",
            "highlight": True,
        }
    ]


@extend_schema(responses=dict)
class OpenTasksView(OrgScopedMixin, APIView):
    """Offene Aufgaben der Organisation, nach den Rechten des Benutzers."""

    def get(self, request, org_id: int):
        org, perms = self.org, self.org_permissions
        items: list[dict] = []
        if org.keeps_members and "members" in (org.enabled_modules or []):
            items += member_tasks(org, perms)
        items += event_tasks(org, perms)
        items += billing_tasks(org, perms)
        from todos.open_tasks import todo_tasks

        items += todo_tasks(request.user, org, perms)
        items.sort(key=lambda item: not item.get("highlight", False))
        return Response({"items": items})
