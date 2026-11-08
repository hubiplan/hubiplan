"""Versammlungen unter „Zu erledigen“ (Menüprüfung 2, N-03): Einladung fällig,
Anträge eingegangen, Protokoll fertigstellen und freigeben. Nur für die Einheit selbst
(nicht ihre Untereinheiten) und nur mit dem Recht, Versammlungen zu bearbeiten."""

from __future__ import annotations

import datetime

from django.db.models import Count, Q
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext, ngettext

from .access import EDIT, MODULE
from .models import Meeting, Motion

# Einladungen erscheinen so viele Tage vor Ablauf der Einladungsfrist
INVITE_AHEAD_DAYS = 7


def _short(day: datetime.date) -> str:
    return date_format(day, "SHORT_DATE_FORMAT", use_l10n=True)


def meeting_tasks(org, perms: set[str]) -> list[dict]:
    if EDIT not in perms or MODULE not in (org.enabled_modules or []):
        return []
    if org.type not in ("club", "federation"):
        return []
    today = timezone.localdate()
    meetings = (
        Meeting.objects.filter(organization=org, department__isnull=True)
        .exclude(status__in=[Meeting.Status.DONE, Meeting.Status.CANCELLED])
        .select_related("event", "kind")
        .annotate(motions_open=Count("motions", filter=Q(motions__status=Motion.Status.SUBMITTED)))
        .order_by("event__starts_at")
    )
    items: list[dict] = []
    for m in meetings:
        day = timezone.localtime(m.event.starts_at).date()
        link = f"/versammlungen?versammlung={m.pk}"
        if m.status == Meeting.Status.DRAFT:
            invite_by = day - datetime.timedelta(days=m.kind.invite_days)
            if invite_by - datetime.timedelta(days=INVITE_AHEAD_DAYS) <= today <= day:
                items.append(
                    {
                        "kind": "meeting_invite",
                        "area": "meetings",
                        "kind_label": gettext("Versammlung"),
                        "title": gettext("Einladung zu „{title}“ versenden").format(
                            title=m.event.title
                        ),
                        "detail": gettext("Einladungsfrist bis {date}").format(
                            date=_short(invite_by)
                        ),
                        "created_at": m.created_at,
                        "link": link,
                        "highlight": today >= invite_by,
                    }
                )
        if m.motions_open:
            items.append(
                {
                    "kind": "meeting_motions",
                    "area": "meetings",
                    "kind_label": gettext("Versammlung"),
                    "title": ngettext(
                        "{n} Antrag zu „{title}“ eingegangen",
                        "{n} Anträge zu „{title}“ eingegangen",
                        m.motions_open,
                    ).format(n=m.motions_open, title=m.event.title),
                    "detail": gettext("aufnehmen oder ablehnen"),
                    "created_at": m.created_at,
                    "link": link,
                }
            )
        if m.status in (Meeting.Status.HELD, Meeting.Status.MINUTES) or (
            m.status == Meeting.Status.INVITED and day < today
        ):
            items.append(
                {
                    "kind": "meeting_minutes",
                    "area": "meetings",
                    "kind_label": gettext("Versammlung"),
                    "title": gettext("Protokoll zu „{title}“ fertigstellen").format(
                        title=m.event.title
                    ),
                    "detail": gettext("am {date}, noch nicht freigegeben").format(date=_short(day)),
                    "created_at": m.created_at,
                    "link": link,
                }
            )
    return items
