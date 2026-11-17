"""Beitragsnachweise unter „Zu erledigen“ (Recht: Mitglieder bearbeiten).

- eingegangene Nachweise prüfen (eine Zeile mit Anzahl)
- Mitglieder, die zwei Beitragsjahre hintereinander keinen Nachweis gebracht haben: Vorschlag,
  die Ermäßigung zu beenden (Fachfrage F9)
"""

from __future__ import annotations

from django.utils import timezone
from django.utils.translation import gettext, ngettext

from access.catalog import MEMBERS_EDIT

from . import services
from .models import DiscountAssignment, FeeProof


def proof_tasks(org, perms: set[str]) -> list[dict]:
    from members.models import today

    if MEMBERS_EDIT not in perms or not services.module_on(org):
        return []
    items = []
    waiting = FeeProof.objects.filter(organization=org, status=FeeProof.Status.RECEIVED).count()
    if waiting:
        items.append(
            {
                "kind": "fee_proofs_review",
                "kind_label": gettext("Beitragsnachweise"),
                "title": ngettext("{n} Nachweis prüfen", "{n} Nachweise prüfen", waiting).format(
                    n=waiting
                ),
                "detail": gettext("für ermäßigte Beiträge"),
                "created_at": timezone.now(),
                "link": "/mitglieder/beitragsnachweise",
                "highlight": False,
            }
        )
    on = today()
    stale = stale_assignments(org, on)
    if stale:
        items.append(
            {
                "kind": "fee_proofs_stale",
                "kind_label": gettext("Beitragsnachweise"),
                "title": ngettext(
                    "{n} Ermäßigung ohne Nachweis seit zwei Jahren",
                    "{n} Ermäßigungen ohne Nachweis seit zwei Jahren",
                    len(stale),
                ).format(n=len(stale)),
                "detail": gettext("Ermäßigung beenden?"),
                "created_at": timezone.now(),
                "link": "/mitglieder/beitragsnachweise?stand=zwei-jahre",
                "highlight": False,
            }
        )
    return items


def stale_assignments(org, on) -> list[DiscountAssignment]:
    """Laufende Zuordnungen ohne anerkannten Nachweis in den letzten zwei abgelaufenen Jahren."""
    rows = list(
        DiscountAssignment.objects.filter(
            organization=org, discount__is_archived=False, valid_until__isnull=True
        ).select_related("discount", "membership__organization")
    )
    if not rows:
        return []
    this_year = org.fiscal_year_of(on)
    result = []
    for a in rows:
        membership = a.membership
        if membership.current_period(on) is None:
            continue
        periods = list(membership.periods.all())
        missing = 0
        for year in (this_year, this_year - 1, this_year - 2):
            start, _end = org.fiscal_range(year)
            if a.valid_from > start:
                continue  # in diesem Jahr noch nicht (ganz) zugeordnet
            st = services.year_state(
                membership, a.discount, year, on, assignments=[a], periods=periods
            )
            if st.state == services.MISSING:
                missing += 1
            elif st.state != services.OPEN:
                break
            if missing >= 2:
                result.append(a)
                break
    return result
