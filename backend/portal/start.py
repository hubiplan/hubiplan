"""Startseite der Apps: ``GET /api/portal/<Zugang>/start/`` liefert in einem Abruf, was der
Reiter „Start“ zeigt::

    {"next_event": {…} | null, "todo": [{"key", "title", "count", "target"}], "tiles": […]}

``next_event``: der nächste Termin, der stattfindet, im Format der Terminliste (mit
``my_response``). ``todo``: was gerade auf die Person wartet, in fester Reihenfolge; ``target``
nennt den Bereich, in den die App führt (unbekannte überspringt sie). ``tiles``: die Kacheln wie
unter ``…/home-tiles/``. Teil der App-Schnittstelle: Felder nur abwärtskompatibel ändern.
"""

from __future__ import annotations

import datetime
import logging

from django.utils import timezone
from django.utils.translation import ngettext
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from core.tenancy import scope_of, set_rls, user_view

logger = logging.getLogger(__name__)

#: So weit schaut „Start“ nach vorn; die ganze Liste steht unter „Termine“.
DAYS_AHEAD = 120


def _events(request, access) -> tuple[dict | None, int]:
    """Nächster Termin und Zahl der Termine, die noch auf eine Rückmeldung warten."""
    from events import services
    from events.models import EventResponse
    from events.recurrence import occurrences
    from events.views import occurrence_data
    from members.models import DepartmentMembership, today
    from oidc import nc_talk

    club = access.organization
    if not services.module_on(club):
        return None, 0
    on = today()
    depts = list(
        DepartmentMembership.objects.filter(membership_id=access.membership_id, valid_from__lte=on)
        .exclude(valid_until__lt=on)
        .values_list("department_id", flat=True)
    )
    viewer = services.member_viewer(
        club, depts, access.membership_id, sees_board=services.is_board(request.user, club)
    )
    now = timezone.now()
    items = [
        o
        for o in occurrences(viewer.events(), now, now + datetime.timedelta(days=DAYS_AHEAD))
        if (o.ends_at >= now or o.event.all_day) and not o.is_cancelled
    ]
    mine = dict(
        EventResponse.objects.filter(
            membership_id=access.membership_id,
            event_id__in={o.event.pk for o in items if o.event.rsvp_enabled},
        ).values_list("event_id", "status")
    )
    # Serien zählen einmal: Die Rückmeldung gilt für alle Termine der Serie
    waiting = {
        o.event.pk
        for o in items
        if o.event.rsvp_enabled
        and o.event.pk not in mine
        and (o.event.rsvp_deadline is None or o.event.rsvp_deadline > now)
    }
    if not items:
        return None, 0
    first = items[0]
    return occurrence_data(first, viewer, mine, nc_talk.rooms_for([first])), len(waiting)


def _todo(access, open_rsvps: int) -> list[dict]:
    """Was auf die Person wartet. Jede Zeile nur, wenn die Zahl über null liegt."""
    from . import views

    club = access.organization
    rows: list[dict] = []

    def add(key: str, target: str, count, title) -> None:
        try:
            n = int(count())
        except Exception:  # pragma: no cover - ein Bereich darf die Startseite nie sprengen
            logger.exception("Startseite %s: Zählen fehlgeschlagen", key)
            return
        if n > 0:
            rows.append({"key": key, "title": title(n).format(n=n), "count": n, "target": target})

    add(
        "rsvp",
        "events",
        lambda: open_rsvps,
        lambda n: ngettext(
            "{n} Termin wartet auf deine Rückmeldung",
            "{n} Termine warten auf deine Rückmeldung",
            n,
        ),
    )
    add(
        "surveys",
        "surveys",
        lambda: views._open_surveys(club, access.membership_id),
        lambda n: ngettext(
            "{n} Umfrage wartet auf deine Antwort", "{n} Umfragen warten auf deine Antwort", n
        ),
    )
    add(
        "orders",
        "orders",
        lambda: views._orders_open(club, access),
        lambda n: ngettext("{n} Sammelbestellung läuft", "{n} Sammelbestellungen laufen", n),
    )
    add(
        "fee_proofs",
        "fee_proofs",
        lambda: views._fee_proofs(access)["fee_proofs_due"],
        lambda n: ngettext("{n} Beitragsnachweis fehlt", "{n} Beitragsnachweise fehlen", n),
    )
    add(
        "expenses",
        "expenses",
        lambda: views._expense_questions(access),
        lambda n: ngettext(
            "{n} Rückfrage zu deinen Auslagen", "{n} Rückfragen zu deinen Auslagen", n
        ),
    )
    add(
        "training",
        "training",
        lambda: views._training(access)["training_checkin"],
        lambda n: ngettext(
            "{n} Training zum Einchecken offen", "{n} Trainings zum Einchecken offen", n
        ),
    )
    add(
        "pinboard",
        "pinboard",
        lambda: views._pinboard_new(club, access),
        lambda n: ngettext(
            "{n} neuer Beitrag an der Pinnwand", "{n} neue Beiträge an der Pinnwand", n
        ),
    )
    return rows


class PortalStartView(APIView):
    """Startseite der Apps für einen Zugang."""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        from .views import _portal_access

        with user_view(request.user.pk):
            access = _portal_access(request.user, kwargs["access_id"])
        set_rls(access.organization_id, request.user.pk, scope_id=scope_of(access.organization_id))
        self.access = access

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(responses=dict)
    def get(self, request, **kwargs):
        from hometiles import portal_tiles
        from hometiles.base import run

        next_event, open_rsvps = _events(request, self.access)
        return Response(
            {
                "next_event": next_event,
                "todo": _todo(self.access, open_rsvps),
                "tiles": run(
                    portal_tiles.TILES,
                    portal_tiles.PortalContext(self.access, request.user),
                    request.user,
                    f"p{self.access.pk}",
                ),
            }
        )
